"""Control-plane command vocabulary and message shape."""

from enum import StrEnum, auto
from typing import Any

from pydantic import BaseModel


class CommandType(StrEnum):
    """Control-plane command vocabulary. Values are the wire strings."""

    AUTHENTICATE_HARNESS = auto()
    INSTALL_HARNESS = auto()


COMMAND_TYPES: frozenset[CommandType] = frozenset(CommandType)


class Command(BaseModel):
    """Control-plane request directed at a runtime."""

    type: CommandType
    devcontainer_id: str | None = None
    payload: dict[str, Any] | None = None
