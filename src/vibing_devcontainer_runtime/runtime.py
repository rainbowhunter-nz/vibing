"""Devcontainer-side runtime skeleton.

The Devcontainer Runtime Agent owns Claude-session lifecycle (eventually:
launching Claude Code, PTY, streaming output, approval detection). This
module only defines the interface and a skeleton implementation. No process
launches, no PTY, no I/O.
"""

from typing import Protocol

from vibing_protocol import Command, CommandType, RuntimeEvent

DEVCONTAINER_COMMAND_TYPES: frozenset[CommandType] = frozenset(
    {
        CommandType.START_AGENT_SESSION,
        CommandType.STOP_AGENT_SESSION,
        CommandType.SEND_USER_INPUT,
        CommandType.RESOLVE_APPROVAL,
    }
)


class DevcontainerRuntime(Protocol):
    """Receive a devcontainer-side command, emit zero or more runtime events."""

    def handle(self, command: Command) -> list[RuntimeEvent]: ...


class DevcontainerRuntimeAgent:
    """Devcontainer runtime agent. Implementation pending — no runtime infra yet."""

    def handle(self, command: Command) -> list[RuntimeEvent]:
        raise NotImplementedError
