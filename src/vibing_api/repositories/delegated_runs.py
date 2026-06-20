"""Delegated-run projection persistence. Repository executes; caller commits."""

import json
import sqlite3
from datetime import datetime, timezone

from pydantic import BaseModel
from vibing_protocol import DelegatedRunItem


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DelegatedRunRow(BaseModel):
    run_id: str
    harness: str
    model: str
    status: str
    result: str | None = None
    error: dict | None = None
    started_at: str


class DelegatedRunRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def replace(self, devcontainer_id: str, items: list[DelegatedRunItem]) -> None:
        self._conn.execute(
            "DELETE FROM delegated_runs WHERE devcontainer_id = ?", (devcontainer_id,)
        )
        now = _now()
        self._conn.executemany(
            "INSERT INTO delegated_runs "
            "(devcontainer_id, run_id, harness, model, status, result, error, started_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    devcontainer_id,
                    it.run_id,
                    it.harness,
                    it.model,
                    it.status,
                    it.result,
                    json.dumps(it.error) if it.error is not None else None,
                    it.started_at,
                    now,
                )
                for it in items
            ],
        )

    def list(self, devcontainer_id: str) -> list[DelegatedRunRow]:
        rows = self._conn.execute(
            "SELECT run_id, harness, model, status, result, error, started_at "
            "FROM delegated_runs WHERE devcontainer_id = ? ORDER BY run_id",
            (devcontainer_id,),
        ).fetchall()
        return [
            DelegatedRunRow(
                run_id=r["run_id"],
                harness=r["harness"],
                model=r["model"],
                status=r["status"],
                result=r["result"],
                error=json.loads(r["error"]) if r["error"] else None,
                started_at=r["started_at"],
            )
            for r in rows
        ]
