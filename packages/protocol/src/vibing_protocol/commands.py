"""Control-plane command vocabulary and message shape.

A Command represents user intent or a control-plane request directed at a
runtime (host or devcontainer). This module defines the allowed command types
and the typed message shape. Dispatch and execution live in consumers.
"""

from typing import Any, Literal, get_args

from pydantic import BaseModel

CommandType = Literal[
    "start_devcontainer",
    "stop_devcontainer",
    "restart_devcontainer",
    "start_agent_session",
    "stop_agent_session",
    "send_user_input",
    "resolve_approval",
]

COMMAND_TYPES: frozenset[str] = frozenset(get_args(CommandType))


class Command(BaseModel):
    """Control-plane request directed at a runtime."""

    type: CommandType
    devcontainer_id: str | None = None
    agent_session_id: str | None = None
    payload: dict[str, Any] | None = None
