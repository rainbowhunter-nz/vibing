"""Shared control-plane message shapes for Vibing host and devcontainer runtimes."""

from .commands import COMMAND_TYPES, Command, CommandType
from .messages import (
    CommandEnvelope,
    HarnessStatusEnvelope,
    HarnessStatusItem,
    RegisterEnvelope,
)

__all__ = [
    "COMMAND_TYPES",
    "Command",
    "CommandEnvelope",
    "CommandType",
    "HarnessStatusEnvelope",
    "HarnessStatusItem",
    "RegisterEnvelope",
]
