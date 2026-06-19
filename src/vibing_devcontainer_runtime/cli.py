"""Command-line entry point for the Devcontainer Runtime Agent.

Connects to the Control Plane agent channel, registers with a devcontainer_id, and runs
two concurrent jobs in one asyncio loop (ADR-0011): the Command/event WebSocket client
(Agent Sessions) and the MCP server the main harness calls to spawn Delegated Runs.
"""

import asyncio
from pathlib import Path

import typer
from logzero import logger
from mcp.server.fastmcp import FastMCP
from vibing_protocol import RegisterEnvelope, RuntimeEventSource
from vibing_runtime_client import RuntimeChannelClient

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner
from vibing_devcontainer_runtime.command_handler import AgentCommandHandler, _make_emit
from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager
from vibing_devcontainer_runtime.harness.process import real_process_factory
from vibing_devcontainer_runtime.harness.registry import build_adapters
from vibing_devcontainer_runtime.harness_manager import HarnessManager
from vibing_devcontainer_runtime.mcp_server import build_mcp_server
from vibing_devcontainer_runtime.transcript import TranscriptReader

DEFAULT_CONTROL_PLANE_URL = "ws://host.docker.internal:8000/api/v1/runtime/agent/ws"

cli = typer.Typer(
    add_completion=False,
    help="Devcontainer Runtime Agent: Agent Sessions + harness delegation MCP server.",
)


async def _serve_async(
    control_plane_url: str, devcontainer_id: str, mcp_host: str, mcp_port: int, workspace: str
) -> None:
    adapters = build_adapters(real_process_factory, Path.home())
    harness_manager = HarnessManager(adapters)

    register = RegisterEnvelope(
        source=RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT, devcontainer_id=devcontainer_id
    )
    handler = AgentCommandHandler(ClaudeCodeRunner(), harness_manager=harness_manager)
    client = RuntimeChannelClient(control_plane_url, register, handler.handle)
    client.on_request("transcript_request", TranscriptReader().respond)

    # Delegated runs emit over the same channel; reuse the client's send via a forwarding emit.
    emit = _make_emit(client.send_envelope)
    delegated_runs = DelegatedRunManager(
        adapters,
        real_process_factory,
        emit,
        devcontainer_id=devcontainer_id,
        workspace=workspace,
    )
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
        "Starting devcontainer runtime agent (cp=%s, dc=%s, mcp=%s:%d, ws=%s)",
        control_plane_url,
        devcontainer_id,
        mcp_host,
        mcp_port,
        workspace,
    )
    _serve_blocking(control_plane_url, devcontainer_id, mcp_host, mcp_port, workspace)


def main() -> None:
    cli()
