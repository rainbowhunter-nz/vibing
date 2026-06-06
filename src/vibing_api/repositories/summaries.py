"""Session-summary persistence. Repository executes; caller commits."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

_COLUMNS = (
    "id, agent_session_id, final_status, started_at, ended_at, "
    "last_known_event, summary_text, created_at"
)


@dataclass(frozen=True)
class SessionSummary:
    id: str
    agent_session_id: str
    final_status: str
    started_at: str | None
    ended_at: str | None
    last_known_event: str | None
    summary_text: str | None
    created_at: str


def _row_to_summary(row: sqlite3.Row) -> SessionSummary:
    return SessionSummary(
        id=row["id"],
        agent_session_id=row["agent_session_id"],
        final_status=row["final_status"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        last_known_event=row["last_known_event"],
        summary_text=row["summary_text"],
        created_at=row["created_at"],
    )


class SessionSummaryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def create(
        self,
        agent_session_id: str,
        final_status: str,
        started_at: str | None = None,
        ended_at: str | None = None,
        last_known_event: str | None = None,
        summary_text: str | None = None,
    ) -> SessionSummary:
        summary = SessionSummary(
            id=str(uuid.uuid4()),
            agent_session_id=agent_session_id,
            final_status=final_status,
            started_at=started_at,
            ended_at=ended_at,
            last_known_event=last_known_event,
            summary_text=summary_text,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._conn.execute(
            f"INSERT INTO session_summaries ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                summary.id,
                summary.agent_session_id,
                summary.final_status,
                summary.started_at,
                summary.ended_at,
                summary.last_known_event,
                summary.summary_text,
                summary.created_at,
            ),
        )
        return summary

    def upsert(
        self,
        agent_session_id: str,
        final_status: str,
        started_at: str | None = None,
        ended_at: str | None = None,
        last_known_event: str | None = None,
        summary_text: str | None = None,
    ) -> SessionSummary:
        """One summary per session (ADR-0008): update in place if present, else insert."""
        existing = self.get_by_session(agent_session_id)
        if existing is None:
            return self.create(
                agent_session_id,
                final_status,
                started_at=started_at,
                ended_at=ended_at,
                last_known_event=last_known_event,
                summary_text=summary_text,
            )
        self._conn.execute(
            "UPDATE session_summaries SET final_status = ?, started_at = ?, ended_at = ?, "
            "last_known_event = ?, summary_text = ? WHERE agent_session_id = ?",
            (
                final_status,
                started_at,
                ended_at,
                last_known_event,
                summary_text,
                agent_session_id,
            ),
        )
        return SessionSummary(
            id=existing.id,
            agent_session_id=agent_session_id,
            final_status=final_status,
            started_at=started_at,
            ended_at=ended_at,
            last_known_event=last_known_event,
            summary_text=summary_text,
            created_at=existing.created_at,
        )

    def get(self, summary_id: str) -> SessionSummary | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM session_summaries WHERE id = ?",
            (summary_id,),
        ).fetchone()
        return _row_to_summary(row) if row is not None else None

    def get_by_session(self, agent_session_id: str) -> SessionSummary | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM session_summaries WHERE agent_session_id = ?",
            (agent_session_id,),
        ).fetchone()
        return _row_to_summary(row) if row is not None else None
