import pytest

from vibing_protocol import Command
from vibing_devcontainer_runtime import (
    DEVCONTAINER_COMMAND_TYPES,
    DevcontainerRuntime,
    DevcontainerRuntimeAgent,
)


def test_devcontainer_runtime_agent_satisfies_protocol() -> None:
    runtime: DevcontainerRuntime = DevcontainerRuntimeAgent()
    assert callable(runtime.handle)


def test_devcontainer_runtime_agent_handle_is_unimplemented() -> None:
    runtime = DevcontainerRuntimeAgent()
    with pytest.raises(NotImplementedError):
        runtime.handle(
            Command(type="start_agent_session", devcontainer_id="dc1", agent_session_id="s1")
        )


def test_devcontainer_command_types_cover_session_surface() -> None:
    assert DEVCONTAINER_COMMAND_TYPES == {
        "start_agent_session",
        "stop_agent_session",
        "send_user_input",
        "resolve_approval",
    }
