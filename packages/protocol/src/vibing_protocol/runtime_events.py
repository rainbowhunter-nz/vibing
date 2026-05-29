"""Runtime-event vocabulary and message shape.

A RuntimeEvent is a structured event emitted by a runtime (host or devcontainer)
to the control plane. This module defines the allowed event types, the source
literal, and the typed message shape. Persistence lives in consumers.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field

EventType = Literal[
    "devcontainer_started",
    "devcontainer_failed",
    "devcontainer_stopped",
    "agent_session_started",
    "agent_asked_question",
    "approval_requested",
    "approval_resolved",
    "session_completed",
    "session_failed",
    "session_stopped",
]

RuntimeEventSource = Literal[
    "host_runtime_worker",
    "devcontainer_runtime_agent",
]

EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))
RUNTIME_EVENT_SOURCES: frozenset[str] = frozenset(get_args(RuntimeEventSource))


class InvalidRuntimeEventError(ValueError):
    """Raised when an event_type or source is not in the allowed vocabulary."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeEvent(BaseModel):
    """Structured event emitted by a runtime to the control plane."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    devcontainer_id: str | None = None
    agent_session_id: str | None = None
    event_type: EventType
    source: RuntimeEventSource
    payload: dict[str, Any] | None = None
    created_at: str = Field(default_factory=_now_iso)
