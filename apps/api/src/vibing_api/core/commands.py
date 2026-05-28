"""Backwards-compatible re-exports for command vocabulary.

The canonical home is vibing_protocol.commands. This shim keeps existing
imports (e.g. `from vibing_api.core.commands import COMMAND_TYPES`) working.
"""

from vibing_protocol.commands import COMMAND_TYPES, Command, CommandType

__all__ = ["COMMAND_TYPES", "Command", "CommandType"]
