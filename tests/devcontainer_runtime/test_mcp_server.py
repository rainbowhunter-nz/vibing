import asyncio
from typing import Any

from vibing_harness import CommandResult, Executor, HarnessDescriptor
from vibing_devcontainer_runtime.mcp_server import build_mcp_server


class FakeExecutor:
    async def run(self, argv: list[str]) -> CommandResult:
        return CommandResult(0, "", "")

    async def read(self, path: str) -> bytes | None:
        return None

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        pass


class FakeDescriptor(HarnessDescriptor):
    def __init__(self, name: str, installed: bool, authenticated: bool) -> None:
        self.name = name
        self._installed = installed
        self._authenticated = authenticated

    async def is_installed(self, ex: Executor) -> bool:
        return self._installed

    def install_argv(self) -> list[str]:
        return []

    async def install(self, ex: Executor) -> None: ...

    async def is_authenticated(self, ex: Executor) -> bool:
        return self._authenticated

    async def write_credentials(self, ex: Executor, blob: dict) -> None: ...

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return []

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()


class FakeDelegatedRuns:
    def __init__(self) -> None:
        self.spawned: list[tuple[Any, ...]] = []
        self.awaited: tuple[str, float] | None = None

    async def spawn(self, harness, model, prompt, title, *, cwd=None, detached=False):
        self.spawned.append((harness, model, prompt, title, cwd, detached))
        return {"run_id": "run-1", "status": "completed", "result": "ok"}

    def get_result(self, run_id):
        return {"run_id": run_id, "status": "completed", "result": "ok", "error": {}}

    def list_runs(self):
        return [
            {
                "run_id": "run-1",
                "title": "t",
                "harness": "codex",
                "model": "gpt-5.5",
                "status": "running",
            }
        ]

    async def stop(self, run_id):
        return {"run_id": run_id, "status": "stopped"}

    async def await_run(self, run_id, timeout=25.0):
        self.awaited = (run_id, timeout)
        return {"run_id": run_id, "status": "completed", "result": "ok", "error": {}}


def _descriptors_map():
    return {
        "codex": FakeDescriptor("codex", installed=True, authenticated=True),
        "cursor": FakeDescriptor("cursor", installed=False, authenticated=False),
    }


def test_tools_are_registered():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_harnesses", "spawn", "list_runs", "get_run", "stop", "await_run"} <= names
    assert "get_status" not in names and "get_result" not in names


def test_server_has_external_subagent_instructions():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    assert mcp.instructions and "external subagent" in mcp.instructions.lower()


def test_get_run_returns_status_result_error():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    _content, result = asyncio.run(mcp.call_tool("get_run", {"run_id": "run-1"}))
    assert result["status"] == "completed" and result["result"] == "ok" and "error" in result


def test_list_runs_tool_returns_titles():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    _content, result = asyncio.run(mcp.call_tool("list_runs", {}))
    items = result["result"] if isinstance(result, dict) and "result" in result else result
    assert items[0]["title"] == "t"


def test_list_harnesses_returns_statuses():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    _content, result = asyncio.run(mcp.call_tool("list_harnesses", {}))
    harnesses = result["result"] if isinstance(result, dict) and "result" in result else result
    names = {h["name"] for h in harnesses}
    assert names == {"codex", "cursor"}


def test_spawn_forwards_args_and_returns_outcome():
    runs = FakeDelegatedRuns()
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), runs)
    _content, result = asyncio.run(
        mcp.call_tool(
            "spawn", {"harness": "codex", "model": "gpt-5.5", "prompt": "go", "title": "demo"}
        )
    )
    assert runs.spawned == [("codex", "gpt-5.5", "go", "demo", None, False)]
    assert result["status"] == "completed" and result["result"] == "ok"


def test_await_run_forwards_args_and_returns_result():
    runs = FakeDelegatedRuns()
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), runs)
    _content, result = asyncio.run(
        mcp.call_tool("await_run", {"run_id": "run-1", "timeout_seconds": 5.0})
    )
    assert runs.awaited == ("run-1", 5.0)
    assert result["status"] == "completed" and result["result"] == "ok"
