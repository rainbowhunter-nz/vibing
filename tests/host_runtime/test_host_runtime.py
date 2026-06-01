import pytest

from vibing_host_runtime import HOST_COMMAND_TYPES, HostRuntime, HostRuntimeWorker
from vibing_protocol import COMMAND_TYPES, Command


def test_host_runtime_worker_satisfies_protocol() -> None:
    runtime: HostRuntime = HostRuntimeWorker()
    assert callable(runtime.handle)


def test_host_runtime_worker_handle_is_unimplemented() -> None:
    runtime = HostRuntimeWorker()
    with pytest.raises(NotImplementedError):
        runtime.handle(Command(type="start_devcontainer", devcontainer_id="dc1"))


def test_host_command_types_cover_devcontainer_lifecycle() -> None:
    assert HOST_COMMAND_TYPES == {
        "start_devcontainer",
        "stop_devcontainer",
    }


def test_restart_devcontainer_not_in_vocabulary() -> None:
    assert "restart_devcontainer" not in COMMAND_TYPES
    assert "restart_devcontainer" not in HOST_COMMAND_TYPES
