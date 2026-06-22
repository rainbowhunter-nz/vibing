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


def test_inject_runs_bootstrap_then_spawn_with_same_url(tmp_path: Path) -> None:
    payloads = []

    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[:2] == ["devcontainer", "exec"]:
            payloads.append(command[-1])
        return RunResult(0, "", "")

    injector = RuntimeInjector(
        runner=runner,
        wheel_dir=_wheel_dir(tmp_path),
        runtime_control_plane_url="ws://cp:8080/api/v1/runtime/agent/ws",
    )
    assert asyncio.run(injector.inject_by_path("dc1", "/work/repo")) is True

    assert len(payloads) == 2
    bootstrap, spawn = payloads

    # half 1: install synchronously + preflight, NOT the runtime
    assert "set -e" in bootstrap and "pipefail" in bootstrap
    assert f"tee {CONTAINER_LOG_PATH}" in bootstrap
    assert (
        "vibing runtime preflight --control-plane-url ws://cp:8080/api/v1/runtime/agent/ws"
        in bootstrap
    )
    assert "nohup" not in bootstrap

    # half 2: detached runtime + PID, same resolved url
    assert "nohup vibing runtime devcontainer" in spawn
    assert "--control-plane-url ws://cp:8080/api/v1/runtime/agent/ws" in spawn
    assert f"echo $! >{CONTAINER_PID_PATH}" in spawn


def test_inject_skips_spawn_when_bootstrap_fails(tmp_path: Path) -> None:
    payloads = []

    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[:2] == ["devcontainer", "exec"]:
            payloads.append(command[-1])
            if "preflight" in command[-1]:
                return RunResult(1, "", "PREFLIGHT FAILED: control plane unreachable")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir=_wheel_dir(tmp_path))
    assert asyncio.run(injector.inject_by_path("dc1", "/work/repo")) is False

    # only the bootstrap exec ran; spawn was skipped
    assert len(payloads) == 1
    assert "nohup" not in payloads[0]


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


def test_stream_log_yields_streamer_chunks(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        return RunResult(0, "", "")

    async def fake_streamer(engine, container_id):
        assert container_id == "deadbeef"
        yield b"install ok\n"
        yield b"runtime started\n"

    injector = RuntimeInjector(runner=runner, log_streamer=fake_streamer)

    async def collect():
        return [chunk async for chunk in injector.stream_log("/work/repo")]

    assert asyncio.run(collect()) == [b"install ok\n", b"runtime started\n"]


def test_stream_log_empty_when_no_container(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "\n", "")  # no container id

    async def fake_streamer(engine, container_id):
        yield b"should not be reached"

    injector = RuntimeInjector(runner=runner, log_streamer=fake_streamer)

    async def collect():
        return [chunk async for chunk in injector.stream_log("/work/repo")]

    assert asyncio.run(collect()) == []
