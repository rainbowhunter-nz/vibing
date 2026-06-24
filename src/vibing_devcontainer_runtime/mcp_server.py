"""build_mcp_server: the in-container MCP server the main harness calls (ADR-0011/0013).

Streamable-HTTP, stateless, JSON responses. Tools delegate to vibing_harness descriptors
(status) and DelegatedRunManager (spawn/status/result/stop).
"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from vibing_harness import Executor, HarnessDescriptor

from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager


def build_mcp_server(
    executor: Executor,
    descriptors_map: dict[str, HarnessDescriptor],
    delegated_runs: DelegatedRunManager,
    *,
    host: str = "127.0.0.1",
    port: int = 8848,
) -> FastMCP:
    mcp = FastMCP("vibing-harness", host=host, port=port, stateless_http=True, json_response=True)

    @mcp.tool()
    async def list_harnesses() -> list[dict[str, Any]]:
        """List managed coding harnesses with installed/authenticated status."""
        out = []
        for d in descriptors_map.values():
            s = await d.status(executor)
            out.append({"name": s.name, "installed": s.installed, "authenticated": s.authenticated})
        return out

    @mcp.tool()
    async def spawn(
        harness: str, model: str, prompt: str, detached: bool = False, cwd: str | None = None
    ) -> dict[str, Any]:
        """Spawn a Delegated Run. Blocks for the result unless detached=true."""
        return await delegated_runs.spawn(harness, model, prompt, cwd=cwd, detached=detached)

    @mcp.tool()
    def get_status(run_id: str) -> dict[str, Any]:
        """Get the status of a detached Delegated Run."""
        return delegated_runs.get_status(run_id)

    @mcp.tool()
    def get_result(run_id: str) -> dict[str, Any]:
        """Get the result of a finished Delegated Run."""
        return delegated_runs.get_result(run_id)

    @mcp.tool()
    async def await_run(run_id: str, timeout_seconds: float = 25.0) -> dict[str, Any]:
        """Block until a detached Delegated Run finishes; return its result. Re-call if timed_out."""
        return await delegated_runs.await_run(run_id, timeout=timeout_seconds)

    @mcp.tool()
    async def stop(run_id: str) -> dict[str, Any]:
        """Stop a running Delegated Run."""
        return await delegated_runs.stop(run_id)

    return mcp
