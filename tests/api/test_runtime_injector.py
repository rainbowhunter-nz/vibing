import asyncio
from pathlib import Path

from vibing_api.core.devcontainer_cli import RunResult
from vibing_api.core.runtime_injector import (
    CONTAINER_LOG_PATH,
    CONTAINER_PID_PATH,
    RuntimeInjector,
)


def _wheel_dir(tmp_path: Path) -> str:
    (tmp_path / "vibing-0.1.0-py3-none-any.whl").write_text("")
    return str(tmp_path)


def test_inject_by_path_resolves_container_then_injects(tmp_path: Path) -> None:
    calls = []

    async def runner(command):
        calls.append(command)
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir=_wheel_dir(tmp_path))
    ok = asyncio.run(injector.inject_by_path("dc1", "/work/repo"))
    assert ok is True
    assert any(
        c[:3] == ["docker", "ps", "-q"] and "label=devcontainer.local_folder=/work/repo" in c
        for c in calls
    )


def test_inject_payload_installs_synchronously_and_detaches_only_runtime(tmp_path: Path) -> None:
    payloads = []

    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[:2] == ["devcontainer", "exec"]:
            payloads.append(command[-1])
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir=_wheel_dir(tmp_path))
    asyncio.run(injector.inject_by_path("dc1", "/work/repo"))
    assert len(payloads) == 1
    payload = payloads[0]
    # install runs synchronously (not backgrounded) and tees into the unified log
    assert "set -e" in payload and "pipefail" in payload
    assert f"tee {CONTAINER_LOG_PATH}" in payload
    # only the long-running runtime is detached, and its PID is recorded
    assert "nohup vibing runtime devcontainer" in payload
    assert f"echo $! >{CONTAINER_PID_PATH}" in payload
    # the whole chain is NOT backgrounded (no trailing "&" on the install/export)
    assert "vibing &" not in payload


def test_inject_returns_false_when_a_step_fails(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[0] == "docker" and command[1] == "cp":
            return RunResult(1, "", "no such file")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir=_wheel_dir(tmp_path))
    assert asyncio.run(injector.inject_by_path("dc1", "/work/repo")) is False


def test_stop_runtime_kills_via_pid_file(tmp_path: Path) -> None:
    calls = []

    async def runner(command):
        calls.append(command)
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner)
    ok = asyncio.run(injector.stop_runtime("/work/repo"))
    assert ok is True
    exec_calls = [c for c in calls if c[:2] == ["docker", "exec"]]
    assert exec_calls and CONTAINER_PID_PATH in exec_calls[0][-1]


def test_read_log_returns_container_file_contents(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[:2] == ["docker", "exec"]:
            return RunResult(0, "install ok\nruntime started\n", "")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner)
    log = asyncio.run(injector.read_log("/work/repo"))
    assert log == "install ok\nruntime started\n"


def test_read_log_returns_none_when_no_container(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "\n", "")  # no container id
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner)
    assert asyncio.run(injector.read_log("/work/repo")) is None
