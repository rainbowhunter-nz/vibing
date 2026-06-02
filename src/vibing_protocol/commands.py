"""Control-plane command vocabulary and message shape.

A Command represents user intent or a control-plane request directed at a
runtime (host or devcontainer). This module defines the allowed command types
and the typed message shape. Dispatch and execution live in consumers.
"""

from enum import StrEnum, auto
from typing import Any

from pydantic import BaseModel


class CommandType(StrEnum):
    """Control-plane command vocabulary. Values are the wire strings."""

    START_DEVCONTAINER = auto()
    STOP_DEVCONTAINER = auto()
    START_AGENT_SESSION = auto()
    STOP_AGENT_SESSION = auto()
    SEND_USER_INPUT = auto()
    RESOLVE_APPROVAL = auto()


COMMAND_TYPES: frozenset[CommandType] = frozenset(CommandType)


class Command(BaseModel):
    """Control-plane request directed at a runtime."""

    type: CommandType
    devcontainer_id: str | None = None
    agent_session_id: str | None = None
    payload: dict[str, Any] | None = None
