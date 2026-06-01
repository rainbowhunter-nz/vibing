from fastapi import APIRouter, Request, status
from vibing_protocol import Command

from vibing_api.api.schemas.agent_sessions import AgentSession, AgentSessionStartRequest
from vibing_api.core.database import get_connection
from vibing_api.core.errors import (
    ActiveAgentSessionError,
    AgentSessionNotFoundError,
    DevcontainerNotFoundError,
    InactiveAgentSessionError,
    InvalidDevcontainerStateError,
    RuntimeUnavailableError,
)
from vibing_api.core.runtime_channel import AgentRegistry
from vibing_api.repositories.agent_sessions import AgentSessionRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository

router = APIRouter(tags=["agent-sessions"], prefix="/devcontainers")

_ACTIVE_STATUSES = frozenset({"starting", "running", "waiting_for_approval"})


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
    if devcontainer.status != "running":
        raise InvalidDevcontainerStateError(
            "start agent session", devcontainer.status, frozenset({"running"})
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
        session = AgentSessionRepository(conn).create(devcontainer_id)
        conn.commit()

    await agent_manager.send_command(
        Command(
            type="start_agent_session",
            devcontainer_id=devcontainer_id,
            agent_session_id=session.id,
            payload={"prompt": payload.prompt},
        )
    )
    return AgentSession(**vars(session))


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
            type="stop_agent_session",
            devcontainer_id=devcontainer_id,
            agent_session_id=session_id,
        )
    )
    return AgentSession(**vars(session))
