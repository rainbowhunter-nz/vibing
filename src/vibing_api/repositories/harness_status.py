"""Harness status persistence. Repository executes; caller commits."""

import sqlite3
from datetime import datetime, timezone

from pydantic import BaseModel


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HarnessStatusRow(BaseModel):
    name: str
    installed: bool
    authenticated: bool


class HarnessStatusRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def upsert(
        self,
        devcontainer_id: str,
        name: str,
        *,
        installed: bool,
        authenticated: bool,
    ) -> None:
        self._conn.execute(
            "INSERT INTO harness_status (devcontainer_id, name, installed, authenticated, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(devcontainer_id, name) DO UPDATE SET "
            "installed = excluded.installed, authenticated = excluded.authenticated, updated_at = excluded.updated_at",
            (devcontainer_id, name, int(installed), int(authenticated), _now()),
        )

    def list(self, devcontainer_id: str) -> list[HarnessStatusRow]:
        rows = self._conn.execute(
            "SELECT name, installed, authenticated FROM harness_status WHERE devcontainer_id = ? ORDER BY name",
            (devcontainer_id,),
        ).fetchall()
        return [
            HarnessStatusRow(
                name=row["name"],
                installed=bool(row["installed"]),
                authenticated=bool(row["authenticated"]),
            )
            for row in rows
        ]
