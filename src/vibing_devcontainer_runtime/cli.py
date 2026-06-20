"""Command-line entry point for the Devcontainer Runtime.

Connects to the Control Plane harness command channel, reports initial harness status on
connect, and concurrently runs the MCP delegation server (ADR-0011, ADR-0015).
"""

import asyncio
from pathlib import Path

import typer
from logzero import logger
from mcp.server.fastmcp import FastMCP
from vibing_protocol import DelegatedRunItem, DelegatedRunsEnvelope, RegisterEnvelope

from vibing_devcontainer_runtime.command_handler import HarnessCommandHandler
from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager
from vibing_devcontainer_runtime.harness.process import real_process_factory
from vibing_devcontainer_runtime.harness.registry import build_adapters
from vibing_devcontainer_runtime.harness_manager import HarnessManager
from vibing_devcontainer_runtime.mcp_server import build_mcp_server
from vibing_devcontainer_runtime.runtime_client import RuntimeChannelClient

DEFAULT_CONTROL_PLANE_URL = "ws://host.docker.internal:8080/api/v1/runtime/agent/ws"

cli = typer.Typer(
    add_completion=False,
    help="Devcontainer Runtime: harness management + MCP delegation server.",
)


async def _serve_async(
    control_plane_url: str, devcontainer_id: str, mcp_host: str, mcp_port: int, workspace: str
) -> None:
    adapters = build_adapters(real_process_factory, Path.home())
    harness_manager = HarnessManager(adapters)

    register = RegisterEnvelope(devcontainer_id=devcontainer_id)
    handler = HarnessCommandHandler(harness_manager, devcontainer_id)

    delegated_runs = DelegatedRunManager(
        adapters,
        real_process_factory,
        devcontainer_id=devcontainer_id,
        workspace=workspace,
    )

    async def _report_runs() -> None:
        items = [DelegatedRunItem(**r) for r in delegated_runs.list_runs()]
        try:
            await client.send_envelope(
                DelegatedRunsEnvelope(devcontainer_id=devcontainer_id, items=items)
            )
        except Exception:
            logger.exception("Failed to report delegated runs")

    async def _on_registered() -> None:
        await handler.report_all(client.send_envelope)
        await _report_runs()

    client = RuntimeChannelClient(
        control_plane_url, register, handler.handle, on_registered=_on_registered
    )
    delegated_runs.report = _report_runs

    mcp: FastMCP = build_mcp_server(harness_manager, delegated_runs, host=mcp_host, port=mcp_port)

    await asyncio.gather(
        client.run(),
        mcp.run_streamable_http_async(),
    )


def _serve_blocking(
    control_plane_url: str, devcontainer_id: str, mcp_host: str, mcp_port: int, workspace: str
) -> None:
    try:
        asyncio.run(_serve_async(control_plane_url, devcontainer_id, mcp_host, mcp_port, workspace))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


@cli.callback(invoke_without_command=True)
def serve(
    control_plane_url: str = typer.Option(DEFAULT_CONTROL_PLANE_URL, help="Control Plane WS URL"),
    devcontainer_id: str = typer.Option(..., help="Unique ID of this devcontainer"),
    mcp_host: str = typer.Option("127.0.0.1", help="MCP server bind host"),
    mcp_port: int = typer.Option(8848, help="MCP server bind port"),
    workspace: str = typer.Option(".", help="Default working dir for Delegated Runs"),
) -> None:
    """Connect to the Control Plane and serve the harness-delegation MCP server."""
    logger.info(
        "Starting devcontainer runtime (cp=%s, dc=%s, mcp=%s:%d, ws=%s)",
        control_plane_url,
        devcontainer_id,
        mcp_host,
        mcp_port,
        workspace,
    )
    _serve_blocking(control_plane_url, devcontainer_id, mcp_host, mcp_port, workspace)


def main() -> None:
    cli()
