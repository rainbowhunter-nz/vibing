import pytest

from vibing_protocol import Command
from vibing_workspace_runtime import (
    WORKSPACE_COMMAND_TYPES,
    WorkspaceRuntime,
    WorkspaceRuntimeAgent,
)


def test_workspace_runtime_agent_satisfies_protocol() -> None:
    runtime: WorkspaceRuntime = WorkspaceRuntimeAgent()
    assert callable(runtime.handle)


def test_workspace_runtime_agent_handle_is_unimplemented() -> None:
    runtime = WorkspaceRuntimeAgent()
    with pytest.raises(NotImplementedError):
        runtime.handle(
            Command(type="start_claude_session", workspace_id="ws1", agent_session_id="s1")
        )


def test_workspace_command_types_cover_session_surface() -> None:
    assert WORKSPACE_COMMAND_TYPES == {
        "start_claude_session",
        "stop_claude_session",
        "send_user_input",
        "resolve_approval",
    }
