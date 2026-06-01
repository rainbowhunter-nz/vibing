"""Devcontainer persistence. Repository executes; caller commits."""

import sqlite3
import uuid
from datetime import datetime, timezone

from vibing_api.api.schemas.devcontainers import Devcontainer
from vibing_api.core.vocabularies import DevcontainerStatus

_INITIAL_STATUS: DevcontainerStatus = "created"
_COLUMNS = "id, name, local_path, status, created_at, updated_at"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_devcontainer(row: sqlite3.Row) -> Devcontainer:
    return Devcontainer(
        id=row["id"],
        name=row["name"],
        local_path=row["local_path"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class DevcontainerRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def create(self, name: str, local_path: str) -> Devcontainer:
        devcontainer_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            f"INSERT INTO devcontainers ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
            (devcontainer_id, name, local_path, _INITIAL_STATUS, now, now),
        )
        return Devcontainer(
            id=devcontainer_id,
            name=name,
            local_path=local_path,
            status=_INITIAL_STATUS,
            created_at=now,
            updated_at=now,
        )

    def list(self) -> list[Devcontainer]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM devcontainers ORDER BY created_at"
        ).fetchall()
        return [_row_to_devcontainer(row) for row in rows]

    def get(self, devcontainer_id: str) -> Devcontainer | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM devcontainers WHERE id = ?",
            (devcontainer_id,),
        ).fetchone()
        return _row_to_devcontainer(row) if row is not None else None

    def update(
        self,
        devcontainer_id: str,
        *,
        name: str | None = None,
        status: DevcontainerStatus | None = None,
    ) -> Devcontainer | None:
        current = self.get(devcontainer_id)
        if current is None:
            return None
        updates = {
            field: value
            for field, value in (("name", name), ("status", status))
            if value is not None
        }
        if not updates:
            return current
        set_clause = ", ".join(f"{field} = ?" for field in updates)
        self._conn.execute(
            f"UPDATE devcontainers SET {set_clause}, updated_at = ? WHERE id = ?",
            (*updates.values(), _now(), devcontainer_id),
        )
        return self.get(devcontainer_id)

    def delete(self, devcontainer_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM devcontainers WHERE id = ?", (devcontainer_id,))
        return cursor.rowcount > 0
