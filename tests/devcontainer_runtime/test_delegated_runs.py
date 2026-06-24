# tests/devcontainer_runtime/test_delegated_runs.py
import asyncio
from typing import Any

import pytest

from vibing_harness import CommandResult, Executor, HarnessDescriptor
from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager
from vibing_devcontainer_runtime.process import CompletedCommand, HarnessProcess


class FakeExecutor:
    async def run(self, argv: list[str]) -> CommandResult:
        return CommandResult(0, "", "")

    async def read(self, path: str) -> bytes | None:
        return None

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        pass


class FakeDescriptor(HarnessDescriptor):
    name = "codex"

    def __init__(self, authed: bool = True) -> None:
        self._authed = authed

    async def is_installed(self, ex: Executor) -> bool:
        return True

    def install_argv(self) -> list[str]:
        return []

    async def install(self, ex: Executor) -> None: ...

    async def is_authenticated(self, ex: Executor) -> bool:
        return self._authed

    async def write_credentials(self, ex: Executor, blob: dict) -> None: ...

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return ["codex", "exec", prompt]

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
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


def _mgr(**kwargs: Any) -> DelegatedRunManager:
    return DelegatedRunManager(
        kwargs.pop("descriptors_map", {"codex": FakeDescriptor()}),
        kwargs.pop("executor", FakeExecutor()),
        kwargs.pop("factory", lambda *a: ScriptedProcess(CompletedCommand(0, "ok", ""))),
        devcontainer_id=kwargs.pop("devcontainer_id", "dc-1"),
        workspace=kwargs.pop("workspace", "/ws"),
        **kwargs,
    )


def test_blocking_spawn_returns_result():
    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "the answer\n", ""))

    mgr = _mgr(factory=factory)
    out = asyncio.run(mgr.spawn("codex", "gpt-5.4", "do it"))
    assert out == {"run_id": "run-1", "status": "completed", "result": "the answer"}


def test_spawn_uses_workspace_as_default_cwd_and_spawn_env():
    captured: dict[str, Any] = {}

    def factory(argv, cwd, env):
        captured["cwd"] = cwd
        captured["env"] = env
        return ScriptedProcess(CompletedCommand(0, "ok", ""))

    mgr = _mgr(factory=factory)
    asyncio.run(mgr.spawn("codex", "m", "p"))
    assert captured["cwd"] == "/ws"


def test_failed_run_status():
    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(2, "", "boom"))

    mgr = _mgr(factory=factory)
    out = asyncio.run(mgr.spawn("codex", "m", "p"))
    assert out["status"] == "failed"
    assert mgr.get_result("run-1")["error"]["exit_code"] == 2


def test_unauthenticated_harness_raises():
    mgr = _mgr(descriptors_map={"codex": FakeDescriptor(authed=False)})
    with pytest.raises(RuntimeError, match="not authenticated"):
        asyncio.run(mgr.spawn("codex", "m", "p"))


def test_detached_spawn_returns_running_then_pollable():
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "late result", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=factory)
        started = await mgr.spawn("codex", "m", "p", detached=True)
        assert started == {"run_id": "run-1", "status": "running"}
        assert mgr.get_status("run-1")["status"] == "running"
        gate.set()
        await mgr.wait_all()
        assert mgr.get_status("run-1")["status"] == "completed"
        assert mgr.get_result("run-1")["result"] == "late result"

    asyncio.run(scenario())


def test_capacity_cap_rejects_when_full():
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=factory, max_concurrent=1)
        await mgr.spawn("codex", "m", "p", detached=True)
        with pytest.raises(RuntimeError, match="at capacity"):
            await mgr.spawn("codex", "m", "p", detached=True)
        gate.set()
        await mgr.wait_all()

    asyncio.run(scenario())


def test_stop_preserves_terminal_status_of_completed_run():
    proc = ScriptedProcess(CompletedCommand(0, "done", ""))

    async def scenario():
        mgr = _mgr(factory=lambda *a: proc)
        await mgr.spawn("codex", "m", "p")  # blocking — completes before stop
        out = await mgr.stop("run-1")
        assert out["status"] == "completed"
        assert mgr.get_status("run-1")["status"] == "completed"

    asyncio.run(scenario())


def test_stop_terminates_detached_run():
    gate = asyncio.Event()
    proc = ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=lambda *a: proc)
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


def test_report_hook_fires_and_lists_runs():
    reports: list[list[dict]] = []

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "ok", ""))

    mgr = _mgr(factory=factory)

    async def _report():
        reports.append(mgr.list_runs())

    async def scenario():
        mgr.report = _report
        out = await mgr.spawn("codex", "m", "do it")
        assert out["status"] in {"completed", "failed"}
        assert len(reports) >= 2
        last = mgr.list_runs()
        assert last[0]["run_id"] == out["run_id"]
        assert last[0]["started_at"]

    asyncio.run(scenario())


def test_wait_exception_marks_failed_and_frees_slot():
    async def scenario():
        mgr = _mgr(factory=lambda *a: BoomProcess(), max_concurrent=1)
        # blocking spawn — must return failed without raising
        out = await mgr.spawn("codex", "m", "p")
        assert out["status"] == "failed"

        # slot must be freed — second spawn must not raise "at capacity"
        out2 = await mgr.spawn("codex", "m", "p")
        assert out2["status"] == "failed"

    asyncio.run(scenario())


def test_await_run_returns_when_detached_run_completes():
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "late result", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=factory)
        await mgr.spawn("codex", "m", "p", detached=True)
        waiter = asyncio.ensure_future(mgr.await_run("run-1"))
        assert not waiter.done()  # blocks while running
        gate.set()
        out = await waiter
        assert out["status"] == "completed"
        assert out["result"] == "late result"

    asyncio.run(scenario())


def test_await_run_returns_immediately_when_already_terminal():
    async def scenario():
        mgr = _mgr(factory=lambda *a: ScriptedProcess(CompletedCommand(0, "done", "")))
        await mgr.spawn("codex", "m", "p")  # blocking -> already completed
        out = await mgr.await_run("run-1")
        assert out["status"] == "completed"
        assert out["result"] == "done"

    asyncio.run(scenario())


def test_await_run_times_out_while_running():
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=factory)
        await mgr.spawn("codex", "m", "p", detached=True)
        out = await mgr.await_run("run-1", timeout=0.01)
        assert out == {"run_id": "run-1", "status": "running", "timed_out": True}
        gate.set()
        await mgr.wait_all()

    asyncio.run(scenario())


def test_await_run_returns_when_run_stopped():
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=factory)
        await mgr.spawn("codex", "m", "p", detached=True)
        waiter = asyncio.ensure_future(mgr.await_run("run-1"))
        await mgr.stop("run-1")
        out = await waiter
        assert out["status"] == "stopped"

    asyncio.run(scenario())


def test_await_run_unknown_id_raises():
    async def scenario():
        mgr = _mgr()
        with pytest.raises(KeyError):
            await mgr.await_run("nope")

    asyncio.run(scenario())
