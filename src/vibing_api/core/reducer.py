"""Projection reducer: the sole writer of state derived from runtime events.

Two layers live here:
- a pure layer (`reduce`, `inbox_event_type_for`) that maps an event to intended
  writes with no I/O, and
- a persistence wrapper (`project`) that applies those writes via the repositories
  inside the caller's transaction (it does not commit).
"""

import sqlite3
from dataclasses import dataclass

from vibing_protocol import EventType, RuntimeEvent

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

_INBOX_EVENT_TYPE: dict[EventType, InboxEventType] = {
    EventType.AGENT_ASKED_QUESTION: InboxEventType.QUESTION,
    EventType.APPROVAL_REQUESTED: InboxEventType.APPROVAL_REQUEST,
    EventType.SESSION_COMPLETED: InboxEventType.COMPLETION,
    EventType.SESSION_FAILED: InboxEventType.FAILURE,
}


def inbox_event_type_for(event_type: EventType) -> InboxEventType | None:
    """The single mapping from runtime event types to inbox event types."""
    return _INBOX_EVENT_TYPE.get(event_type)


@dataclass(frozen=True)
class ProjectionUpdates:
    devcontainer_status: DevcontainerStatus | None = None
    session_status: AgentSessionStatus | None = None
    create_approval: bool = False
    requested_action: str = ""
    resolve_approval: ApprovalStatus | None = None
    resolve_approval_id: str | None = None
    inbox_event_type: InboxEventType | None = None
    resolve_linked_inbox: bool = False
    resolve_inbox_event_id: str | None = None
    final_status: AgentSessionStatus | None = None


def reduce(event: RuntimeEvent) -> ProjectionUpdates:
    """Pure mapping from a runtime event to its intended read-model writes."""
    event_type = event.event_type
    payload = event.payload or {}
    inbox_event_type = inbox_event_type_for(event_type)

    if event_type == EventType.DEVCONTAINER_STARTING:
        return ProjectionUpdates(devcontainer_status=DevcontainerStatus.STARTING)
    if event_type == EventType.DEVCONTAINER_STARTED:
        return ProjectionUpdates(devcontainer_status=DevcontainerStatus.RUNNING)
    if event_type == EventType.DEVCONTAINER_STOPPING:
        return ProjectionUpdates(devcontainer_status=DevcontainerStatus.STOPPING)
    if event_type == EventType.DEVCONTAINER_STOPPED:
        return ProjectionUpdates(devcontainer_status=DevcontainerStatus.STOPPED)
    if event_type == EventType.DEVCONTAINER_FAILED:
        return ProjectionUpdates(devcontainer_status=DevcontainerStatus.ERROR)
    if event_type == EventType.AGENT_SESSION_STARTED:
        return ProjectionUpdates(session_status=AgentSessionStatus.RUNNING)
    if event_type == EventType.APPROVAL_REQUESTED:
        return ProjectionUpdates(
            session_status=AgentSessionStatus.WAITING_FOR_APPROVAL,
            create_approval=True,
            requested_action=payload.get("requested_action", ""),
            inbox_event_type=inbox_event_type,
        )
    if event_type == EventType.APPROVAL_RESOLVED:
        # requested_action is optional/informational; resolution is required.
        resolution = payload.get("resolution")
        if resolution not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            raise ValueError(
                "approval_resolved requires payload.resolution in "
                f"approved/rejected, got: {resolution!r}"
            )
        return ProjectionUpdates(
            session_status=AgentSessionStatus.RUNNING,
            resolve_approval=ApprovalStatus(resolution),
            resolve_approval_id=payload.get("approval_request_id"),
            resolve_linked_inbox=True,
        )
    if event_type == EventType.AGENT_ASKED_QUESTION:
        return ProjectionUpdates(inbox_event_type=inbox_event_type)
    if event_type == EventType.USER_INPUT_SENT:
        return ProjectionUpdates(resolve_inbox_event_id=payload.get("inbox_event_id"))
    if event_type == EventType.SESSION_COMPLETED:
        return ProjectionUpdates(
            session_status=AgentSessionStatus.COMPLETED,
            final_status=AgentSessionStatus.COMPLETED,
            inbox_event_type=inbox_event_type,
        )
    if event_type == EventType.SESSION_FAILED:
        return ProjectionUpdates(
            session_status=AgentSessionStatus.FAILED,
            final_status=AgentSessionStatus.FAILED,
            inbox_event_type=inbox_event_type,
        )
    if event_type == EventType.SESSION_STOPPED:
        return ProjectionUpdates(
            session_status=AgentSessionStatus.STOPPED,
            final_status=AgentSessionStatus.STOPPED,
        )
    return ProjectionUpdates()


def project(event: RuntimeEvent, conn: sqlite3.Connection) -> None:
    """Apply the reducer's updates via repositories within the caller's transaction."""
    updates = reduce(event)
    sessions = AgentSessionRepository(conn)
    approvals = ApprovalRepository(conn)
    inbox = InboxRepository(conn)

    if updates.devcontainer_status is not None and event.devcontainer_id is not None:
        DevcontainerRepository(conn).update(
            event.devcontainer_id, status=updates.devcontainer_status
        )

    if updates.session_status is not None and event.agent_session_id is not None:
        sessions.set_status(event.agent_session_id, updates.session_status)

    created_approval_id: str | None = None
    if updates.create_approval and event.agent_session_id is not None:
        session = sessions.get(event.agent_session_id)
        # tolerate out-of-order events: skip if the referenced row isn't present yet
        if session is not None:
            approval = approvals.create(
                devcontainer_id=session.devcontainer_id,
                agent_session_id=event.agent_session_id,
                requested_action=updates.requested_action,
            )
            created_approval_id = approval.id

    if updates.resolve_approval is not None and updates.resolve_approval_id is not None:
        target = approvals.get(updates.resolve_approval_id)
        # tolerate out-of-order events: skip if the referenced row isn't present yet
        if target is not None:
            approvals.resolve(target.id, updates.resolve_approval)
            if updates.resolve_linked_inbox:
                linked = inbox.get_by_approval(target.id)
                # tolerate out-of-order events: skip if the referenced row isn't present yet
                if linked is not None:
                    inbox.resolve(linked.id)

    if updates.resolve_inbox_event_id is not None:
        # tolerate out-of-order events: resolve returns None if absent, which is fine
        inbox.resolve(updates.resolve_inbox_event_id)

    # tolerate out-of-order events: skip if devcontainer_id isn't present yet
    if updates.inbox_event_type is not None and event.devcontainer_id is not None:
        inbox.create(
            devcontainer_id=event.devcontainer_id,
            event_type=updates.inbox_event_type,
            status="unread",
            agent_session_id=event.agent_session_id,
            approval_request_id=created_approval_id,
        )

    if updates.final_status is not None and event.agent_session_id is not None:
        session = sessions.get(event.agent_session_id)
        SessionSummaryRepository(conn).create(
            agent_session_id=event.agent_session_id,
            final_status=updates.final_status,
            last_known_event=event.event_type,
            ended_at=event.created_at,
            started_at=session.started_at if session is not None else None,
        )
