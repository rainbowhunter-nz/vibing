"""Inbox-event persistence. Repository executes; caller commits."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from vibing_api.core.vocabularies import InboxEventStatus, InboxEventType

_COLUMNS = (
    "id, devcontainer_id, agent_session_id, approval_request_id, "
    "event_type, status, content, created_at, updated_at"
)


@dataclass(frozen=True)
class InboxEvent:
    id: str
    devcontainer_id: str
    agent_session_id: str | None
    approval_request_id: str | None
    event_type: InboxEventType
    status: InboxEventStatus
    content: str | None
    created_at: str
    updated_at: str


def _row_to_inbox(row: sqlite3.Row) -> InboxEvent:
    return InboxEvent(
        id=row["id"],
        devcontainer_id=row["devcontainer_id"],
        agent_session_id=row["agent_session_id"],
        approval_request_id=row["approval_request_id"],
        event_type=row["event_type"],
        status=row["status"],
        content=row["content"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class InboxRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def create(
        self,
        devcontainer_id: str,
        event_type: InboxEventType,
        status: InboxEventStatus,
        agent_session_id: str | None = None,
        approval_request_id: str | None = None,
        content: str | None = None,
    ) -> InboxEvent:
        now = datetime.now(timezone.utc).isoformat()
        event = InboxEvent(
            id=str(uuid.uuid4()),
            devcontainer_id=devcontainer_id,
            agent_session_id=agent_session_id,
            approval_request_id=approval_request_id,
            event_type=event_type,
            status=status,
            content=content,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            f"INSERT INTO inbox_events ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.devcontainer_id,
                event.agent_session_id,
                event.approval_request_id,
                event.event_type,
                event.status,
                event.content,
                event.created_at,
                event.updated_at,
            ),
        )
        return event

    def get(self, inbox_event_id: str) -> InboxEvent | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM inbox_events WHERE id = ?",
            (inbox_event_id,),
        ).fetchone()
        return _row_to_inbox(row) if row is not None else None

    def list(
        self,
        *,
        status: str | None = None,
        devcontainer_id: str | None = None,
        agent_session_id: str | None = None,
    ) -> list[InboxEvent]:
        conditions: list[str] = []
        params: list[str] = []
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if devcontainer_id is not None:
            conditions.append("devcontainer_id = ?")
            params.append(devcontainer_id)
        if agent_session_id is not None:
            conditions.append("agent_session_id = ?")
            params.append(agent_session_id)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM inbox_events{where} ORDER BY created_at",
            params,
        ).fetchall()
        return [_row_to_inbox(row) for row in rows]

    def get_by_approval(self, approval_request_id: str) -> InboxEvent | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM inbox_events WHERE approval_request_id = ?",
            (approval_request_id,),
        ).fetchone()
        return _row_to_inbox(row) if row is not None else None

    def resolve(self, inbox_event_id: str) -> InboxEvent | None:
        if self.get(inbox_event_id) is None:
            return None
        self._conn.execute(
            "UPDATE inbox_events SET status = 'resolved', updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), inbox_event_id),
        )
        return self.get(inbox_event_id)

    def mark_read(self, inbox_event_id: str) -> InboxEvent | None:
        current = self.get(inbox_event_id)
        if current is None:
            return None
        if current.status != InboxEventStatus.UNREAD:
            return current
        self._conn.execute(
            "UPDATE inbox_events SET status = 'read', updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), inbox_event_id),
        )
        return self.get(inbox_event_id)
