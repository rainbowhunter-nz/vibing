import asyncio
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessStatus
from vibing_devcontainer_runtime.mcp_server import build_mcp_server


class FakeHarnessManager:
    async def list_statuses(self) -> list[HarnessStatus]:
        return [HarnessStatus("codex", True, True), HarnessStatus("cursor", False, False)]


class FakeDelegatedRuns:
    def __init__(self) -> None:
        self.spawned: list[tuple[Any, ...]] = []

    async def spawn(self, harness, model, prompt, *, cwd=None, detached=False):
        self.spawned.append((harness, model, prompt, cwd, detached))
        return {"run_id": "run-1", "status": "completed", "result": "ok"}

    def get_status(self, run_id):
        return {"run_id": run_id, "status": "running"}

    def get_result(self, run_id):
        return {"run_id": run_id, "status": "completed", "result": "ok", "error": {}}

    async def stop(self, run_id):
        return {"run_id": run_id, "status": "stopped"}


def test_tools_are_registered():
    mcp = build_mcp_server(FakeHarnessManager(), FakeDelegatedRuns())
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_harnesses", "spawn", "get_status", "get_result", "stop"} <= names


def test_list_harnesses_returns_statuses():
    mcp = build_mcp_server(FakeHarnessManager(), FakeDelegatedRuns())
    _content, result = asyncio.run(mcp.call_tool("list_harnesses", {}))
    # structured tool output wraps a list under "result"
    harnesses = result["result"] if isinstance(result, dict) and "result" in result else result
    names = {h["name"] for h in harnesses}
    assert names == {"codex", "cursor"}


def test_spawn_forwards_args_and_returns_outcome():
    runs = FakeDelegatedRuns()
    mcp = build_mcp_server(FakeHarnessManager(), runs)
    _content, result = asyncio.run(
        mcp.call_tool("spawn", {"harness": "codex", "model": "gpt-5.4", "prompt": "go"})
    )
    assert runs.spawned == [("codex", "gpt-5.4", "go", None, False)]
    assert result["status"] == "completed" and result["result"] == "ok"
