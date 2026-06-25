"""build_mcp_server: the in-container MCP server the main harness calls (ADR-0011/0013).

Streamable-HTTP, stateless, JSON responses. Tools delegate to vibing_harness descriptors
(status) and DelegatedRunManager (spawn/list_runs/get_run/await_run/stop).
"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from vibing_harness import Executor, HarnessDescriptor

from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager


_INSTRUCTIONS = """\
This server provides EXTERNAL SUBAGENTS: full coding-harness runs you dispatch work to,
complementing the in-process Task subagents of subagent-driven-development. When the user
says "use external subagent", dispatch the work here.

Dispatch protocol:
1. spawn(harness, prompt, title, detached=true) -> run_id. `title` is a short human label
   shown in the UI. Omit `model` to use the harness's recommended default; only pass it to
   override. Discover defaults via list_harnesses (each harness reports `default_model`).
2. Run `vibing delegated wait <run_id>` as a BACKGROUND shell command; its completion
   auto-wakes you with the result. Do not poll get_run in a loop.
3. get_run(run_id) -> status + result + error. list_runs() -> all runs. stop(run_id) cancels.

Model rule of thumb (defaults, applied automatically when `model` is omitted):
- cursor  -> composer-2.5: fast, cheap, good default.
- codex   -> gpt-5.5: autonomous CLI coding.
Pass `model` only to override these. See docs/external-subagent-guide.md for task -> model routing.
"""


def build_mcp_server(
    executor: Executor,
    descriptors_map: dict[str, HarnessDescriptor],
    delegated_runs: DelegatedRunManager,
    *,
    host: str = "127.0.0.1",
    port: int = 8848,
) -> FastMCP:
    mcp = FastMCP(
        "vibing-harness",
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
        instructions=_INSTRUCTIONS,
    )

    @mcp.tool()
    async def list_harnesses() -> list[dict[str, Any]]:
        """List managed coding harnesses with installed/authenticated status and the
        `default_model` used when `spawn` is called without a model."""
        out = []
        for d in descriptors_map.values():
            s = await d.status(executor)
            out.append(
                {
                    "name": s.name,
                    "installed": s.installed,
                    "authenticated": s.authenticated,
                    "default_model": s.default_model,
                }
            )
        return out

    @mcp.tool()
    async def spawn(
        harness: str,
        prompt: str,
        title: str,
        model: str | None = None,
        detached: bool = False,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        """Spawn an external-subagent Delegated Run. `title` is a short UI label.
        Omit `model` to use the harness's recommended default (see list_harnesses);
        only pass it to override. Blocks for the result unless detached=true."""
        return await delegated_runs.spawn(harness, model, prompt, title, cwd=cwd, detached=detached)

    @mcp.tool()
    def list_runs() -> list[dict[str, Any]]:
        """List dispatched Delegated Runs (run_id, title, harness, model, status)."""
        return delegated_runs.list_runs()

    @mcp.tool()
    def get_run(run_id: str) -> dict[str, Any]:
        """Get a Delegated Run's status, result, and error."""
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
