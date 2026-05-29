"""Agent-session persistence. Repository executes; caller commits."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from vibing_api.core.vocabularies import AgentSessionStatus

_COLUMNS = (
    "id, devcontainer_id, status, started_at, ended_at, last_event_at, created_at, updated_at"
)


@dataclass(frozen=True)
class AgentSession:
    id: str
    devcontainer_id: str
    status: AgentSessionStatus
    started_at: str | None
    ended_at: str | None
    last_event_at: str | None
    created_at: str
    updated_at: str


def _row_to_session(row: sqlite3.Row) -> AgentSession:
    return AgentSession(
        id=row["id"],
        devcontainer_id=row["devcontainer_id"],
        status=row["status"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        last_event_at=row["last_event_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class AgentSessionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def create(self, devcontainer_id: str, status: AgentSessionStatus = "starting") -> AgentSession:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session = AgentSession(
            id=session_id,
            devcontainer_id=devcontainer_id,
            status=status,
            started_at=None,
            ended_at=None,
            last_event_at=None,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            f"INSERT INTO agent_sessions ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session.id,
                session.devcontainer_id,
                session.status,
                session.started_at,
                session.ended_at,
                session.last_event_at,
                session.created_at,
                session.updated_at,
            ),
        )
        return session

    def get(self, session_id: str) -> AgentSession | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM agent_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return _row_to_session(row) if row is not None else None

    def set_status(self, session_id: str, status: AgentSessionStatus) -> AgentSession | None:
        if self.get(session_id) is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE agent_sessions SET status = ?, updated_at = ?, last_event_at = ? WHERE id = ?",
            (status, now, now, session_id),
        )
        return self.get(session_id)
