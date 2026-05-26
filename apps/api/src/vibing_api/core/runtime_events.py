"""Runtime event vocabulary and persistence helpers.

Runtime events are structured events emitted by the Host Runtime Worker or
Workspace Runtime Agent. This module defines the allowed event types and
provides minimal CRUD helpers over the `runtime_events` table. No event bus,
no side effects.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, get_args

from pydantic import BaseModel

EventType = Literal[
    "workspace_started",
    "workspace_failed",
    "claude_session_started",
    "claude_asked_question",
    "approval_requested",
    "approval_resolved",
    "session_completed",
    "session_failed",
]

RuntimeEventSource = Literal[
    "host_runtime_worker",
    "workspace_runtime_agent",
]

EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))
RUNTIME_EVENT_SOURCES: frozenset[str] = frozenset(get_args(RuntimeEventSource))


class InvalidRuntimeEventError(ValueError):
    """Raised when an event_type or source is not in the allowed vocabulary."""


class RuntimeEvent(BaseModel):
    id: str
    workspace_id: str | None
    agent_session_id: str | None
    event_type: str
    source: str
    payload: dict[str, Any] | None
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_runtime_event(
    conn: sqlite3.Connection,
    *,
    event_type: EventType,
    source: RuntimeEventSource,
    workspace_id: str | None = None,
    agent_session_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RuntimeEvent:
    """Insert a runtime event and return it. Caller is responsible for commit."""
    if event_type not in EVENT_TYPES:
        raise InvalidRuntimeEventError(f"Unknown event_type: {event_type!r}")
    if source not in RUNTIME_EVENT_SOURCES:
        raise InvalidRuntimeEventError(f"Unknown source: {source!r}")

    event_id = str(uuid.uuid4())
    created_at = _now()
    payload_json = json.dumps(payload) if payload is not None else None
    conn.execute(
        "INSERT INTO runtime_events "
        "(id, workspace_id, agent_session_id, event_type, source, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (event_id, workspace_id, agent_session_id, event_type, source, payload_json, created_at),
    )
    return RuntimeEvent(
        id=event_id,
        workspace_id=workspace_id,
        agent_session_id=agent_session_id,
        event_type=event_type,
        source=source,
        payload=payload,
        created_at=created_at,
    )


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
