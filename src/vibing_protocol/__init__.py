"""Shared control-plane message shapes for Vibing host and devcontainer runtimes."""

from .commands import COMMAND_TYPES, Command, CommandType
from .messages import (
    CommandEnvelope,
    DelegatedRunItem,
    DelegatedRunsEnvelope,
    HarnessStatusEnvelope,
    HarnessStatusItem,
    RegisterEnvelope,
)

__all__ = [
    "COMMAND_TYPES",
    "Command",
    "CommandEnvelope",
    "CommandType",
    "DelegatedRunItem",
    "DelegatedRunsEnvelope",
    "HarnessStatusEnvelope",
    "HarnessStatusItem",
    "RegisterEnvelope",
]
