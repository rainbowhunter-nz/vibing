"""Approval-request persistence. Repository executes; caller commits."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from vibing_api.core.vocabularies import ApprovalStatus

_COLUMNS = (
    "id, devcontainer_id, agent_session_id, status, "
    "requested_action, created_at, decided_at"
)


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    devcontainer_id: str
    agent_session_id: str
    status: ApprovalStatus
    requested_action: str
    created_at: str
    decided_at: str | None


def _row_to_approval(row: sqlite3.Row) -> ApprovalRequest:
    return ApprovalRequest(
        id=row["id"],
        devcontainer_id=row["devcontainer_id"],
        agent_session_id=row["agent_session_id"],
        status=row["status"],
        requested_action=row["requested_action"],
        created_at=row["created_at"],
        decided_at=row["decided_at"],
    )


class ApprovalRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def create(
        self,
        devcontainer_id: str,
        agent_session_id: str,
        requested_action: str,
        status: ApprovalStatus = "pending",
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            id=str(uuid.uuid4()),
            devcontainer_id=devcontainer_id,
            agent_session_id=agent_session_id,
            status=status,
            requested_action=requested_action,
            created_at=datetime.now(timezone.utc).isoformat(),
            decided_at=None,
        )
        self._conn.execute(
            f"INSERT INTO approval_requests ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                approval.id,
                approval.devcontainer_id,
                approval.agent_session_id,
                approval.status,
                approval.requested_action,
                approval.created_at,
                approval.decided_at,
            ),
        )
        return approval

    def get(self, approval_id: str) -> ApprovalRequest | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM approval_requests WHERE id = ?",
            (approval_id,),
        ).fetchone()
        return _row_to_approval(row) if row is not None else None

    def get_pending_by_session(
        self, agent_session_id: str
    ) -> ApprovalRequest | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM approval_requests "
            "WHERE agent_session_id = ? AND status = 'pending' "
            "ORDER BY created_at DESC LIMIT 1",
            (agent_session_id,),
        ).fetchone()
        return _row_to_approval(row) if row is not None else None

    def resolve(
        self, approval_id: str, status: ApprovalStatus
    ) -> ApprovalRequest | None:
        if self.get(approval_id) is None:
            return None
        self._conn.execute(
            "UPDATE approval_requests SET status = ?, decided_at = ? WHERE id = ?",
            (status, datetime.now(timezone.utc).isoformat(), approval_id),
        )
        return self.get(approval_id)
