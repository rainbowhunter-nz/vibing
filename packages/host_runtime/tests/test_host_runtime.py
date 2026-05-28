import pytest

from vibing_host_runtime import HOST_COMMAND_TYPES, HostRuntime, HostRuntimeWorker
from vibing_protocol import Command


def test_host_runtime_worker_satisfies_protocol() -> None:
    runtime: HostRuntime = HostRuntimeWorker()
    assert callable(runtime.handle)


def test_host_runtime_worker_handle_is_unimplemented() -> None:
    runtime = HostRuntimeWorker()
    with pytest.raises(NotImplementedError):
        runtime.handle(Command(type="start_workspace", workspace_id="ws1"))


def test_host_command_types_cover_workspace_lifecycle() -> None:
    assert HOST_COMMAND_TYPES == {"start_workspace", "stop_workspace", "restart_workspace"}
