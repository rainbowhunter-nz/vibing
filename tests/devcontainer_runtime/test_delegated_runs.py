# tests/devcontainer_runtime/test_delegated_runs.py
import asyncio
from typing import Any

import pytest

from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager
from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.process import CompletedCommand, HarnessProcess
from vibing_protocol import RuntimeEvent


class FakeAdapter(HarnessAdapter):
    def __init__(self, authed: bool = True) -> None:
        self.name = "codex"
        self._authed = authed

    async def is_installed(self) -> bool:
        return True

    async def install(self) -> None: ...

    async def is_authenticated(self) -> bool:
        return self._authed

    def write_credentials(self, blob: dict[str, Any]) -> None: ...

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return ["codex", "exec", prompt]

    def spawn_env(self) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()


class ScriptedProcess(HarnessProcess):
    def __init__(self, result: CompletedCommand, gate: asyncio.Event | None = None) -> None:
        self._result = result
        self._gate = gate
        self.terminated = False

    async def wait(self) -> CompletedCommand:
        if self._gate is not None:
            await self._gate.wait()
        return self._result

    async def terminate(self) -> None:
        self.terminated = True
        if self._gate is not None:
            self._gate.set()


def collector():
    events: list[RuntimeEvent] = []

    async def emit(e: RuntimeEvent) -> None:
        events.append(e)

    return events, emit


def test_blocking_spawn_returns_result_and_emits_lifecycle():
    events, emit = collector()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "the answer\n", ""))

    mgr = DelegatedRunManager(
        {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
    )
    out = asyncio.run(mgr.spawn("codex", "gpt-5.4", "do it"))
    assert out == {"run_id": "run-1", "status": "completed", "result": "the answer"}
    types = [e.event_type for e in events]
    assert types == ["delegated_run_started", "delegated_run_completed"]
    assert events[0].payload == {
        "delegated_run_id": "run-1",
        "harness": "codex",
        "model": "gpt-5.4",
    }


def test_spawn_uses_workspace_as_default_cwd_and_spawn_env():
    events, emit = collector()
    captured = {}

    def factory(argv, cwd, env):
        captured["cwd"] = cwd
        captured["env"] = env
        return ScriptedProcess(CompletedCommand(0, "ok", ""))

    mgr = DelegatedRunManager(
        {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
    )
    asyncio.run(mgr.spawn("codex", "m", "p"))
    assert captured["cwd"] == "/ws"


def test_failed_run_emits_failed_event():
    events, emit = collector()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(2, "", "boom"))

    mgr = DelegatedRunManager(
        {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
    )
    out = asyncio.run(mgr.spawn("codex", "m", "p"))
    assert out["status"] == "failed"
    assert events[-1].event_type == "delegated_run_failed"
    assert events[-1].payload["exit_code"] == 2


def test_unauthenticated_harness_raises():
    _, emit = collector()
    mgr = DelegatedRunManager(
        {"codex": FakeAdapter(authed=False)},
        lambda *a: None,
        emit,
        devcontainer_id="dc-1",
        workspace="/ws",
    )
    with pytest.raises(RuntimeError, match="not authenticated"):
        asyncio.run(mgr.spawn("codex", "m", "p"))


def test_detached_spawn_returns_running_then_pollable():
    events, emit = collector()
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "late result", ""), gate=gate)

    async def scenario():
        mgr = DelegatedRunManager(
            {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
        )
        started = await mgr.spawn("codex", "m", "p", detached=True)
        assert started == {"run_id": "run-1", "status": "running"}
        assert mgr.get_status("run-1")["status"] == "running"
        gate.set()
        await mgr.wait_all()
        assert mgr.get_status("run-1")["status"] == "completed"
        assert mgr.get_result("run-1")["result"] == "late result"

    asyncio.run(scenario())


def test_capacity_cap_rejects_when_full():
    events, emit = collector()
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    async def scenario():
        mgr = DelegatedRunManager(
            {"codex": FakeAdapter()},
            factory,
            emit,
            devcontainer_id="dc-1",
            workspace="/ws",
            max_concurrent=1,
        )
        await mgr.spawn("codex", "m", "p", detached=True)
        with pytest.raises(RuntimeError, match="at capacity"):
            await mgr.spawn("codex", "m", "p", detached=True)
        gate.set()
        await mgr.wait_all()

    asyncio.run(scenario())


def test_stop_preserves_terminal_status_of_completed_run():
    events, emit = collector()
    proc = ScriptedProcess(CompletedCommand(0, "done", ""))

    def factory(argv, cwd, env):
        return proc

    async def scenario():
        mgr = DelegatedRunManager(
            {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
        )
        await mgr.spawn("codex", "m", "p")  # blocking — completes before stop
        out = await mgr.stop("run-1")
        assert out["status"] == "completed"
        assert mgr.get_status("run-1")["status"] == "completed"

    asyncio.run(scenario())


def test_stop_terminates_detached_run():
    events, emit = collector()
    gate = asyncio.Event()
    proc = ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    def factory(argv, cwd, env):
        return proc

    async def scenario():
        mgr = DelegatedRunManager(
            {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
        )
        await mgr.spawn("codex", "m", "p", detached=True)
        out = await mgr.stop("run-1")
        assert out["status"] == "stopped"
        assert proc.terminated is True
        await mgr.wait_all()

    asyncio.run(scenario())


class BoomProcess(HarnessProcess):
    """process.wait() raises a non-cancel exception."""

    async def wait(self) -> CompletedCommand:
        raise RuntimeError("io boom")

    async def terminate(self) -> None:
        pass


def test_wait_exception_marks_failed_and_frees_slot():
    events, emit = collector()

    def factory(argv, cwd, env):
        return BoomProcess()

    async def scenario():
        mgr = DelegatedRunManager(
            {"codex": FakeAdapter()},
            factory,
            emit,
            devcontainer_id="dc-1",
            workspace="/ws",
            max_concurrent=1,
        )
        # blocking spawn — must return failed without raising
        out = await mgr.spawn("codex", "m", "p")
        assert out["status"] == "failed"
        assert events[-1].event_type == "delegated_run_failed"

        # slot must be freed — second spawn must not raise "at capacity"
        out2 = await mgr.spawn("codex", "m", "p")
        assert out2["status"] == "failed"

    asyncio.run(scenario())
