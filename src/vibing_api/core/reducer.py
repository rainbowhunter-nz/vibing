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
    "agent_asked_question": "question",
    "approval_requested": "approval_request",
    "session_completed": "completion",
    "session_failed": "failure",
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
    inbox_event_type: InboxEventType | None = None
    resolve_linked_inbox: bool = False
    resolve_inbox_event_id: str | None = None
    final_status: AgentSessionStatus | None = None


def reduce(event: RuntimeEvent) -> ProjectionUpdates:
    """Pure mapping from a runtime event to its intended read-model writes."""
    event_type = event.event_type
    payload = event.payload or {}
    inbox_event_type = inbox_event_type_for(event_type)

    if event_type == "devcontainer_starting":
        return ProjectionUpdates(devcontainer_status="starting")
    if event_type == "devcontainer_started":
        return ProjectionUpdates(devcontainer_status="running")
    if event_type == "devcontainer_stopping":
        return ProjectionUpdates(devcontainer_status="stopping")
    if event_type == "devcontainer_stopped":
        return ProjectionUpdates(devcontainer_status="stopped")
    if event_type == "devcontainer_failed":
        return ProjectionUpdates(devcontainer_status="error")
    if event_type == "agent_session_started":
        return ProjectionUpdates(session_status="running")
    if event_type == "approval_requested":
        return ProjectionUpdates(
            session_status="waiting_for_approval",
            create_approval=True,
            requested_action=payload.get("requested_action", ""),
            inbox_event_type=inbox_event_type,
        )
    if event_type == "approval_resolved":
        # requested_action is optional/informational; resolution is required.
        resolution = payload.get("resolution")
        if resolution not in ("approved", "rejected"):
            raise ValueError(
                "approval_resolved requires payload.resolution in "
                f"approved/rejected, got: {resolution!r}"
            )
        return ProjectionUpdates(
            session_status="running",
            resolve_approval=resolution,
            resolve_linked_inbox=True,
        )
    if event_type == "agent_asked_question":
        return ProjectionUpdates(inbox_event_type=inbox_event_type)
    if event_type == "user_input_sent":
        return ProjectionUpdates(resolve_inbox_event_id=payload.get("inbox_event_id"))
    if event_type == "session_completed":
        return ProjectionUpdates(
            session_status="completed",
            final_status="completed",
            inbox_event_type=inbox_event_type,
        )
    if event_type == "session_failed":
        return ProjectionUpdates(
            session_status="failed",
            final_status="failed",
            inbox_event_type=inbox_event_type,
        )
    if event_type == "session_stopped":
        return ProjectionUpdates(
            session_status="stopped",
            final_status="stopped",
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

    if updates.resolve_approval is not None and event.agent_session_id is not None:
        pending = approvals.get_pending_by_session(event.agent_session_id)
        # tolerate out-of-order events: skip if the referenced row isn't present yet
        if pending is not None:
            approvals.resolve(pending.id, updates.resolve_approval)
            if updates.resolve_linked_inbox:
                linked = inbox.get_by_approval(pending.id)
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
