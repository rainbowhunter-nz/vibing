"""Workspace-side runtime skeleton.

The Workspace Runtime Agent owns Claude-session lifecycle (eventually:
launching Claude Code, PTY, streaming output, approval detection). This
module only defines the interface and a skeleton implementation. No process
launches, no PTY, no I/O.
"""

from typing import Protocol

from vibing_protocol import Command, RuntimeEvent

WORKSPACE_COMMAND_TYPES: frozenset[str] = frozenset(
    {
        "start_claude_session",
        "stop_claude_session",
        "send_user_input",
        "resolve_approval",
    }
)


class WorkspaceRuntime(Protocol):
    """Receive a workspace-side command, emit zero or more runtime events."""

    def handle(self, command: Command) -> list[RuntimeEvent]: ...


class WorkspaceRuntimeAgent:
    """Workspace runtime agent. Implementation pending — no runtime infra yet."""

    def handle(self, command: Command) -> list[RuntimeEvent]:
        raise NotImplementedError
