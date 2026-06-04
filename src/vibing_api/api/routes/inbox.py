from fastapi import APIRouter

from vibing_api.api.schemas.agent_sessions import AgentSession as AgentSessionSchema
from vibing_api.api.schemas.approvals import ApprovalRequest as ApprovalRequestSchema
from vibing_api.api.schemas.inbox import InboxEvent, InboxEventDetail, InboxEventList
from vibing_api.core.database import get_connection
from vibing_api.core.errors import InboxEventNotFoundError
from vibing_api.repositories.agent_sessions import AgentSessionRepository
from vibing_api.repositories.approvals import ApprovalRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.inbox import InboxRepository

router = APIRouter(tags=["inbox"], prefix="/inbox-events")


@router.get("", response_model=InboxEventList)
def list_inbox_events(
    status: str | None = None,
    devcontainer_id: str | None = None,
    agent_session_id: str | None = None,
) -> InboxEventList:
    with get_connection() as conn:
        rows = InboxRepository(conn).list(
            status=status,
            devcontainer_id=devcontainer_id,
            agent_session_id=agent_session_id,
        )
    return InboxEventList(items=[InboxEvent.model_validate(r) for r in rows])


@router.get("/{inbox_event_id}", response_model=InboxEventDetail)
def get_inbox_event(inbox_event_id: str) -> InboxEventDetail:
    with get_connection() as conn:
        event = InboxRepository(conn).get(inbox_event_id)
        if event is None:
            raise InboxEventNotFoundError(inbox_event_id)
        devcontainer = DevcontainerRepository(conn).get(event.devcontainer_id)
        assert devcontainer is not None  # FK guarantees this
        session_row = (
            AgentSessionRepository(conn).get(event.agent_session_id)
            if event.agent_session_id
            else None
        )
        approval_row = (
            ApprovalRepository(conn).get(event.approval_request_id)
            if event.approval_request_id
            else None
        )
    return InboxEventDetail(
        **vars(event),
        devcontainer=devcontainer,
        agent_session=AgentSessionSchema.model_validate(session_row) if session_row else None,
        approval_request=ApprovalRequestSchema.model_validate(approval_row)
        if approval_row
        else None,
    )


@router.post("/{inbox_event_id}/read", response_model=InboxEvent)
def mark_inbox_event_read(inbox_event_id: str) -> InboxEvent:
    with get_connection() as conn:
        event = InboxRepository(conn).mark_read(inbox_event_id)
        if event is None:
            raise InboxEventNotFoundError(inbox_event_id)
        conn.commit()
    return InboxEvent.model_validate(event)


@router.post("/{inbox_event_id}/resolve", response_model=InboxEvent)
def resolve_inbox_event(inbox_event_id: str) -> InboxEvent:
    with get_connection() as conn:
        event = InboxRepository(conn).resolve(inbox_event_id)
        if event is None:
            raise InboxEventNotFoundError(inbox_event_id)
        conn.commit()
    return InboxEvent.model_validate(event)
