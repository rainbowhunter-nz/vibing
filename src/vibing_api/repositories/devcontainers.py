"""Devcontainer persistence (manual records only). Repository executes; caller commits."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from vibing_api.core.discovery import devcontainer_id

_COLUMNS = "id, name, local_path, created_at, updated_at"


@dataclass(frozen=True)
class DevcontainerRecord:
    id: str
    name: str
    local_path: str
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r: sqlite3.Row) -> DevcontainerRecord:
    return DevcontainerRecord(
        id=r["id"],
        name=r["name"],
        local_path=r["local_path"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class DevcontainerRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def create(self, name: str, local_path: str) -> DevcontainerRecord:
        devcontainer_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            f"INSERT INTO devcontainers ({_COLUMNS}) VALUES (?, ?, ?, ?, ?)",
            (devcontainer_id, name, local_path, now, now),
        )
        return DevcontainerRecord(devcontainer_id, name, local_path, now, now)

    def list(self) -> list[DevcontainerRecord]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM devcontainers ORDER BY created_at"
        ).fetchall()
        return [_row(r) for r in rows]

    def get(self, devcontainer_id: str) -> DevcontainerRecord | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM devcontainers WHERE id = ?", (devcontainer_id,)
        ).fetchone()
        return _row(row) if row is not None else None

    def update(self, devcontainer_id: str, *, name: str | None = None) -> DevcontainerRecord | None:
        current = self.get(devcontainer_id)
        if current is None:
            return None
        if name is None:
            return current
        self._conn.execute(
            "UPDATE devcontainers SET name = ?, updated_at = ? WHERE id = ?",
            (name, _now(), devcontainer_id),
        )
        return self.get(devcontainer_id)

    def delete(self, devcontainer_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM devcontainers WHERE id = ?", (devcontainer_id,))
        return cursor.rowcount > 0

    def upsert(self, name: str, local_path: str) -> DevcontainerRecord:
        now = _now()
        self._conn.execute(
            f"INSERT INTO devcontainers ({_COLUMNS}) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(local_path) DO NOTHING",
            (devcontainer_id(local_path), name, local_path, now, now),
        )
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM devcontainers WHERE local_path = ?", (local_path,)
        ).fetchone()
        return _row(row)
