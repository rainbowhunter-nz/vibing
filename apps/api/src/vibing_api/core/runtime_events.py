"""Runtime-event persistence over the runtime_events SQLite table.

Vocabulary and message shape live in vibing_protocol. This module owns
only the read/write helpers.
"""

import json
import sqlite3
from typing import Any

from vibing_protocol.runtime_events import (
    EVENT_TYPES,
    EventType,
    InvalidRuntimeEventError,
    RUNTIME_EVENT_SOURCES,
    RuntimeEvent,
    RuntimeEventSource,
)

__all__ = [
    "EVENT_TYPES",
    "EventType",
    "InvalidRuntimeEventError",
    "RUNTIME_EVENT_SOURCES",
    "RuntimeEvent",
    "RuntimeEventSource",
    "list_runtime_events_by_session",
    "list_runtime_events_by_workspace",
    "record_runtime_event",
]


def record_runtime_event(
    conn: sqlite3.Connection,
    *,
    event_type: EventType,
    source: RuntimeEventSource,
    workspace_id: str | None = None,
    agent_session_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RuntimeEvent:
    """Validate, build, insert, return. Caller is responsible for commit."""
    if event_type not in EVENT_TYPES:
        raise InvalidRuntimeEventError(f"Unknown event_type: {event_type!r}")
    if source not in RUNTIME_EVENT_SOURCES:
        raise InvalidRuntimeEventError(f"Unknown source: {source!r}")

    event = RuntimeEvent(
        event_type=event_type,
        source=source,
        workspace_id=workspace_id,
        agent_session_id=agent_session_id,
        payload=payload,
    )
    payload_json = json.dumps(event.payload) if event.payload is not None else None
    conn.execute(
        "INSERT INTO runtime_events "
        "(id, workspace_id, agent_session_id, event_type, source, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            event.id,
            event.workspace_id,
            event.agent_session_id,
            event.event_type,
            event.source,
            payload_json,
            event.created_at,
        ),
    )
    return event


def _row_to_event(row: sqlite3.Row) -> RuntimeEvent:
    raw_payload = row["payload"]
    return RuntimeEvent(
        id=row["id"],
        workspace_id=row["workspace_id"],
        agent_session_id=row["agent_session_id"],
        event_type=row["event_type"],
        source=row["source"],
        payload=json.loads(raw_payload) if raw_payload is not None else None,
        created_at=row["created_at"],
    )


def list_runtime_events_by_workspace(
    conn: sqlite3.Connection, workspace_id: str
) -> list[RuntimeEvent]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, workspace_id, agent_session_id, event_type, source, payload, created_at "
        "FROM runtime_events WHERE workspace_id = ? ORDER BY created_at, id",
        (workspace_id,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def list_runtime_events_by_session(
    conn: sqlite3.Connection, agent_session_id: str
) -> list[RuntimeEvent]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, workspace_id, agent_session_id, event_type, source, payload, created_at "
        "FROM runtime_events WHERE agent_session_id = ? ORDER BY created_at, id",
        (agent_session_id,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]
