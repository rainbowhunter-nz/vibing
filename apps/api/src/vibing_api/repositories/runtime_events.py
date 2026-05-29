"""Runtime-event persistence. Repository executes; caller commits."""

import json
import sqlite3
from typing import Any

from vibing_protocol.runtime_events import (
    EVENT_TYPES,
    RUNTIME_EVENT_SOURCES,
    EventType,
    InvalidRuntimeEventError,
    RuntimeEvent,
    RuntimeEventSource,
)

_COLUMNS = "id, devcontainer_id, agent_session_id, event_type, source, payload, created_at"


def _row_to_event(row: sqlite3.Row) -> RuntimeEvent:
    raw_payload = row["payload"]
    return RuntimeEvent(
        id=row["id"],
        devcontainer_id=row["devcontainer_id"],
        agent_session_id=row["agent_session_id"],
        event_type=row["event_type"],
        source=row["source"],
        payload=json.loads(raw_payload) if raw_payload is not None else None,
        created_at=row["created_at"],
    )


class RuntimeEventRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def record(
        self,
        *,
        event_type: EventType,
        source: RuntimeEventSource,
        devcontainer_id: str | None = None,
        agent_session_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        if event_type not in EVENT_TYPES:
            raise InvalidRuntimeEventError(f"Unknown event_type: {event_type!r}")
        if source not in RUNTIME_EVENT_SOURCES:
            raise InvalidRuntimeEventError(f"Unknown source: {source!r}")

        event = RuntimeEvent(
            event_type=event_type,
            source=source,
            devcontainer_id=devcontainer_id,
            agent_session_id=agent_session_id,
            payload=payload,
        )
        payload_json = json.dumps(event.payload) if event.payload is not None else None
        self._conn.execute(
            f"INSERT INTO runtime_events ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.devcontainer_id,
                event.agent_session_id,
                event.event_type,
                event.source,
                payload_json,
                event.created_at,
            ),
        )
        return event

    def list_by_devcontainer(self, devcontainer_id: str) -> list[RuntimeEvent]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM runtime_events "
            "WHERE devcontainer_id = ? ORDER BY created_at, id",
            (devcontainer_id,),
        ).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_by_session(self, agent_session_id: str) -> list[RuntimeEvent]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM runtime_events "
            "WHERE agent_session_id = ? ORDER BY created_at, id",
            (agent_session_id,),
        ).fetchall()
        return [_row_to_event(row) for row in rows]
