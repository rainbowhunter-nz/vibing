"""Runtime-event vocabulary and message shape.

A RuntimeEvent is a structured event emitted by a runtime (host or devcontainer)
to the control plane. This module defines the allowed event types, the source
literal, and the typed message shape. Persistence lives in consumers.
"""

import uuid
from datetime import datetime, timezone
from enum import StrEnum, auto
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Runtime-event vocabulary. Values are the wire strings."""

    DEVCONTAINER_STARTING = auto()
    DEVCONTAINER_STARTED = auto()
    DEVCONTAINER_STOPPING = auto()
    DEVCONTAINER_STOPPED = auto()
    DEVCONTAINER_FAILED = auto()
    AGENT_SESSION_STARTED = auto()
    AGENT_ASKED_QUESTION = auto()
    APPROVAL_REQUESTED = auto()
    APPROVAL_RESOLVED = auto()
    USER_INPUT_SENT = auto()
    SESSION_COMPLETED = auto()
    SESSION_FAILED = auto()
    SESSION_STOPPED = auto()


class RuntimeEventSource(StrEnum):
    """Origin of a runtime event. Values are the wire strings."""

    HOST_RUNTIME_WORKER = auto()
    DEVCONTAINER_RUNTIME_AGENT = auto()


EVENT_TYPES: frozenset[EventType] = frozenset(EventType)
RUNTIME_EVENT_SOURCES: frozenset[RuntimeEventSource] = frozenset(RuntimeEventSource)


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
