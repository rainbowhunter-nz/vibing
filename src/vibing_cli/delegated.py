"""`vibing delegated wait <run_id>`: block on the runtime MCP server until a Delegated Run ends.

A backgroundable shim — Claude Code can't background an MCP call, so the harness runs this as a
background Bash command and is auto-woken when it returns. Loops `await_run` past each bounded
server-side timeout until the run is terminal.
"""

import asyncio
from typing import Annotated, Any

import typer
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from rich.console import Console

app = typer.Typer(no_args_is_help=True, help="Delegated Run helpers (MCP client).")

_out = Console()
_err = Console(stderr=True)

DEFAULT_MCP_URL = "http://127.0.0.1:8848/mcp"


async def _await_once(mcp_url: str, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    """One `await_run` MCP call; returns the tool's structured payload."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "await_run", {"run_id": run_id, "timeout_seconds": timeout_seconds}
            )
            return dict(result.structuredContent or {})


async def _poll(mcp_url: str, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    while True:
        payload = await _await_once(mcp_url, run_id, timeout_seconds)
        if not payload.get("timed_out"):
            return payload


@app.command("wait")
def wait(
    run_id: str,
    mcp_url: Annotated[
        str, typer.Option(envvar="VIBING_MCP_URL", help="Runtime MCP server URL.")
    ] = DEFAULT_MCP_URL,
    timeout_seconds: Annotated[float, typer.Option(help="Per-call long-poll timeout.")] = 25.0,
) -> None:
    """Block until the Delegated Run finishes, then print its result."""
    try:
        payload = asyncio.run(_poll(mcp_url, run_id, timeout_seconds))
    except Exception as exc:
        _out.print(f"[bold red]✗ await_run failed[/bold red]: {exc}")
        raise typer.Exit(1) from exc

    status = payload.get("status")
    if status == "completed":
        _out.print(f"[bold green]✓ {run_id} completed[/bold green]")
        _out.print(payload.get("result") or "")
    else:
        _out.print(f"[bold yellow]{run_id} {status}[/bold yellow]")
        if payload.get("error"):
            _out.print(str(payload["error"]))
