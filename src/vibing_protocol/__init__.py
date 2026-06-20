"""Shared control-plane message shapes and wire codec for the Vibing runtime channel."""

from .channel import decode, encode
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
    "decode",
    "encode",
]
