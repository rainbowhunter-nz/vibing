"""Harness credential persistence. Repository executes; caller commits."""

import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HarnessCredentialRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def upsert(self, name: str, blob: dict) -> None:
        self._conn.execute(
            "INSERT INTO harness_credentials (name, blob, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET blob = excluded.blob, updated_at = excluded.updated_at",
            (name, json.dumps(blob), _now()),
        )

    def get(self, name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT blob FROM harness_credentials WHERE name = ?", (name,)
        ).fetchone()
        return json.loads(row["blob"]) if row is not None else None

    def list(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM harness_credentials ORDER BY name").fetchall()
        return [row["name"] for row in rows]
