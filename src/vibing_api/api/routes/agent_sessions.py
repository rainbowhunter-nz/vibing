import asyncio

from fastapi import APIRouter, Request, Response, status
from logzero import logger
from vibing_protocol import Command, CommandType

from vibing_api.api.schemas.agent_sessions import (
    AgentSession,
    AgentSessionDetail,
    AgentSessionList,
    AgentSessionResumeRequest,
    AgentSessionStartRequest,
    AgentSessionTranscript,
    ApprovalResolutionRequest,
    TranscriptState,
    UserInputRequest,
)
from vibing_api.core.config import settings
from vibing_api.core.database import get_connection
from vibing_api.core.errors import (
    ActiveAgentSessionDeleteError,
    ActiveAgentSessionError,
    AgentSessionNotFoundError,
    ApprovalRequestNotFoundError,
    ApprovalRequestNotPendingError,
    DevcontainerNotFoundError,
    InactiveAgentSessionError,
    InboxEventNotActionableError,
    InboxEventNotFoundError,
    InvalidDevcontainerStateError,
    NonRestingAgentSessionError,
    RuntimeUnavailableError,
)
from vibing_api.core.runtime_channel import AgentRegistry
from vibing_api.core.vocabularies import (
    AgentSessionStatus,
    ApprovalStatus,
    DevcontainerStatus,
    InboxEventType,
)
from vibing_api.repositories.agent_sessions import AgentSessionRepository
from vibing_api.repositories.approvals import ApprovalRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.inbox import InboxRepository
from vibing_api.repositories.summaries import SessionSummaryRepository
from vibing_protocol import extract_claude_result_text

router = APIRouter(tags=["agent-sessions"], prefix="/devcontainers")

_ACTIVE_STATUSES = frozenset(
    {
        AgentSessionStatus.STARTING,
        AgentSessionStatus.RUNNING,
        AgentSessionStatus.WAITING_FOR_APPROVAL,
    }
)

_RESTING_STATUSES = frozenset(
    {
        AgentSessionStatus.COMPLETED,
        AgentSessionStatus.FAILED,
        AgentSessionStatus.STOPPED,
    }
)


@router.get(
    "/{devcontainer_id}/agent-sessions",
    response_model=AgentSessionList,
    status_code=status.HTTP_200_OK,
)
def list_agent_sessions(devcontainer_id: str) -> AgentSessionList:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)

    with get_connection() as conn:
        sessions = AgentSessionRepository(conn).list_by_devcontainer(devcontainer_id)
    return AgentSessionList(items=[AgentSession(**vars(s)) for s in sessions])


@router.get(
    "/{devcontainer_id}/agent-sessions/{session_id}",
    response_model=AgentSessionDetail,
    status_code=status.HTTP_200_OK,
)
def get_agent_session(devcontainer_id: str, session_id: str) -> AgentSessionDetail:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)

    with get_connection() as conn:
        session = AgentSessionRepository(conn).get(session_id)
        if session is None or session.devcontainer_id != devcontainer_id:
            raise AgentSessionNotFoundError(session_id)
        summary = SessionSummaryRepository(conn).get_by_session(session_id)

    raw_summary = summary.summary_text if summary is not None else None
    return AgentSessionDetail(
        **vars(session),
        summary_text=(extract_claude_result_text(raw_summary) if raw_summary is not None else None),
    )


@router.get(
    "/{devcontainer_id}/agent-sessions/{session_id}/transcript",
    response_model=AgentSessionTranscript,
    status_code=status.HTTP_200_OK,
)
async def get_agent_session_transcript(
    devcontainer_id: str, session_id: str, request: Request
) -> AgentSessionTranscript:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)

    with get_connection() as conn:
        session = AgentSessionRepository(conn).get(session_id)
        if session is None or session.devcontainer_id != devcontainer_id:
            raise AgentSessionNotFoundError(session_id)
        summary = SessionSummaryRepository(conn).get_by_session(session_id)

    raw_summary = summary.summary_text if summary is not None else None
    summary_text = extract_claude_result_text(raw_summary) if raw_summary is not None else None

    agent_manager: AgentRegistry = request.app.state.agent_manager
    if devcontainer.status != DevcontainerStatus.RUNNING or not agent_manager.is_connected(
        devcontainer_id
    ):
        return AgentSessionTranscript(state="summary_fallback", summary_text=summary_text)

    try:
        turns = await agent_manager.request_transcript(
            devcontainer_id, session_id, timeout=settings.transcript_timeout_seconds
        )
    except (asyncio.TimeoutError, ConnectionError, RuntimeError) as exc:
        logger.warning("Transcript fetch failed (session=%s): %s", session_id, exc)
        return AgentSessionTranscript(state="error", summary_text=summary_text)

    state: TranscriptState = "has_turns" if turns else "empty"
    return AgentSessionTranscript(state=state, turns=turns, summary_text=summary_text)


@router.delete(
    "/{devcontainer_id}/agent-sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_agent_session(devcontainer_id: str, session_id: str) -> Response:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)

    with get_connection() as conn:
        session = AgentSessionRepository(conn).get(session_id)
    if session is None or session.devcontainer_id != devcontainer_id:
        raise AgentSessionNotFoundError(session_id)

    if session.status in _ACTIVE_STATUSES:
        raise ActiveAgentSessionDeleteError(session_id)

    with get_connection() as conn:
        deleted = AgentSessionRepository(conn).delete(session_id)
        conn.commit()
    if not deleted:
        raise AgentSessionNotFoundError(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{devcontainer_id}/agent-sessions",
    response_model=AgentSession,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_agent_session(
    devcontainer_id: str, payload: AgentSessionStartRequest, request: Request
) -> AgentSession:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    if devcontainer.status != DevcontainerStatus.RUNNING:
        raise InvalidDevcontainerStateError(
            "start agent session", devcontainer.status, frozenset({DevcontainerStatus.RUNNING})
        )

    agent_manager: AgentRegistry = request.app.state.agent_manager
    if not agent_manager.is_connected(devcontainer_id):
        raise RuntimeUnavailableError(
            f"No Devcontainer Runtime Agent is connected for devcontainer: {devcontainer_id}"
        )

    with get_connection() as conn:
        active = AgentSessionRepository(conn).get_active_by_devcontainer(devcontainer_id)
    if active is not None:
        raise ActiveAgentSessionError(devcontainer_id)

    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(devcontainer_id, prompt=payload.prompt)
        conn.commit()

    await agent_manager.send_command(
        Command(
            type=CommandType.START_AGENT_SESSION,
            devcontainer_id=devcontainer_id,
            agent_session_id=session.id,
            payload={"prompt": payload.prompt},
        )
    )
    return AgentSession(**vars(session))


@router.post(
    "/{devcontainer_id}/agent-sessions/{session_id}/resume",
    response_model=AgentSession,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_agent_session(
    devcontainer_id: str, session_id: str, body: AgentSessionResumeRequest, request: Request
) -> AgentSession:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    if devcontainer.status != DevcontainerStatus.RUNNING:
        raise InvalidDevcontainerStateError(
            "resume agent session", devcontainer.status, frozenset({DevcontainerStatus.RUNNING})
        )

    with get_connection() as conn:
        session = AgentSessionRepository(conn).get(session_id)
    if session is None or session.devcontainer_id != devcontainer_id:
        raise AgentSessionNotFoundError(session_id)

    if session.status not in _RESTING_STATUSES:
        raise NonRestingAgentSessionError(session_id)

    agent_manager: AgentRegistry = request.app.state.agent_manager
    if not agent_manager.is_connected(devcontainer_id):
        raise RuntimeUnavailableError(
            f"No Devcontainer Runtime Agent is connected for devcontainer: {devcontainer_id}"
        )

    # Target is resting, so any active session is necessarily a different one.
    with get_connection() as conn:
        active = AgentSessionRepository(conn).get_active_by_devcontainer(devcontainer_id)
    if active is not None:
        raise ActiveAgentSessionError(devcontainer_id)

    with get_connection() as conn:
        updated = AgentSessionRepository(conn).set_status(session_id, AgentSessionStatus.STARTING)
        conn.commit()

    await agent_manager.send_command(
        Command(
            type=CommandType.RESUME_AGENT_SESSION,
            devcontainer_id=devcontainer_id,
            agent_session_id=session_id,
            payload={"prompt": body.prompt},
        )
    )
    return AgentSession(**vars(updated if updated is not None else session))


@router.post(
    "/{devcontainer_id}/agent-sessions/{session_id}/stop",
    response_model=AgentSession,
    status_code=status.HTTP_202_ACCEPTED,
)
async def stop_agent_session(
    devcontainer_id: str, session_id: str, request: Request
) -> AgentSession:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)

    with get_connection() as conn:
        session = AgentSessionRepository(conn).get(session_id)
    if session is None or session.devcontainer_id != devcontainer_id:
        raise AgentSessionNotFoundError(session_id)

    if session.status not in _ACTIVE_STATUSES:
        raise InactiveAgentSessionError(session_id)

    agent_manager: AgentRegistry = request.app.state.agent_manager
    if not agent_manager.is_connected(devcontainer_id):
        raise RuntimeUnavailableError(
            f"No Devcontainer Runtime Agent is connected for devcontainer: {devcontainer_id}"
        )

    await agent_manager.send_command(
        Command(
            type=CommandType.STOP_AGENT_SESSION,
            devcontainer_id=devcontainer_id,
            agent_session_id=session_id,
        )
    )
    return AgentSession(**vars(session))


@router.post(
    "/{devcontainer_id}/agent-sessions/{session_id}/user-input",
    response_model=AgentSession,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_user_input(
    devcontainer_id: str, session_id: str, body: UserInputRequest, request: Request
) -> AgentSession:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)

    with get_connection() as conn:
        session = AgentSessionRepository(conn).get(session_id)
    if session is None or session.devcontainer_id != devcontainer_id:
        raise AgentSessionNotFoundError(session_id)

    if session.status not in _ACTIVE_STATUSES:
        raise InactiveAgentSessionError(session_id)

    with get_connection() as conn:
        inbox_event = InboxRepository(conn).get(body.inbox_event_id)
    if (
        inbox_event is None
        or inbox_event.agent_session_id != session_id
        or inbox_event.devcontainer_id != devcontainer_id
    ):
        raise InboxEventNotFoundError(body.inbox_event_id)

    if inbox_event.event_type != InboxEventType.QUESTION or inbox_event.status == "resolved":
        raise InboxEventNotActionableError(body.inbox_event_id)

    agent_manager: AgentRegistry = request.app.state.agent_manager
    if not agent_manager.is_connected(devcontainer_id):
        raise RuntimeUnavailableError(
            f"No Devcontainer Runtime Agent is connected for devcontainer: {devcontainer_id}"
        )

    await agent_manager.send_command(
        Command(
            type=CommandType.SEND_USER_INPUT,
            devcontainer_id=devcontainer_id,
            agent_session_id=session_id,
            payload={"inbox_event_id": body.inbox_event_id, "text": body.text},
        )
    )
    return AgentSession(**vars(session))


@router.post(
    "/{devcontainer_id}/agent-sessions/{session_id}/approval-resolution",
    response_model=AgentSession,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resolve_approval(
    devcontainer_id: str, session_id: str, body: ApprovalResolutionRequest, request: Request
) -> AgentSession:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)

    with get_connection() as conn:
        session = AgentSessionRepository(conn).get(session_id)
    if session is None or session.devcontainer_id != devcontainer_id:
        raise AgentSessionNotFoundError(session_id)

    if session.status not in _ACTIVE_STATUSES:
        raise InactiveAgentSessionError(session_id)

    with get_connection() as conn:
        approval = ApprovalRepository(conn).get(body.approval_request_id)
    if (
        approval is None
        or approval.agent_session_id != session_id
        or approval.devcontainer_id != devcontainer_id
    ):
        raise ApprovalRequestNotFoundError(body.approval_request_id)

    if approval.status != ApprovalStatus.PENDING:
        raise ApprovalRequestNotPendingError(body.approval_request_id)

    agent_manager: AgentRegistry = request.app.state.agent_manager
    if not agent_manager.is_connected(devcontainer_id):
        raise RuntimeUnavailableError(
            f"No Devcontainer Runtime Agent is connected for devcontainer: {devcontainer_id}"
        )

    await agent_manager.send_command(
        Command(
            type=CommandType.RESOLVE_APPROVAL,
            devcontainer_id=devcontainer_id,
            agent_session_id=session_id,
            payload={
                "approval_request_id": body.approval_request_id,
                "resolution": body.resolution,
            },
        )
    )
    return AgentSession(**vars(session))
