"""Command-line entry point for the Devcontainer Runtime Agent.

Connects to the Control Plane agent channel, registers with a devcontainer_id,
and handles Commands via AgentCommandHandler (runs Claude on start_agent_session).
"""

import asyncio

import typer
from logzero import logger
from vibing_protocol import RegisterEnvelope, RuntimeEventSource
from vibing_runtime_client import RuntimeChannelClient

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner
from vibing_devcontainer_runtime.command_handler import AgentCommandHandler
from vibing_devcontainer_runtime.transcript import TranscriptReader

DEFAULT_CONTROL_PLANE_URL = "ws://host.docker.internal:8000/api/v1/runtime/agent/ws"

cli = typer.Typer(
    add_completion=False,
    help="Devcontainer Runtime Agent: connects to the Control Plane and runs Claude on commands.",
)


@cli.callback(invoke_without_command=True)
def serve(
    control_plane_url: str = typer.Option(
        DEFAULT_CONTROL_PLANE_URL, help="Control Plane agent WebSocket URL"
    ),
    devcontainer_id: str = typer.Option(..., help="Unique ID of this devcontainer"),
) -> None:
    """Connect to the Control Plane, register, and handle Commands."""
    logger.info(
        "Starting devcontainer runtime agent (control_plane=%s, devcontainer_id=%s)",
        control_plane_url,
        devcontainer_id,
    )
    register = RegisterEnvelope(
        source=RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT, devcontainer_id=devcontainer_id
    )
    handler = AgentCommandHandler(ClaudeCodeRunner()).handle
    transcript_handler = TranscriptReader().read
    client = RuntimeChannelClient(
        control_plane_url, register, handler, transcript_handler=transcript_handler
    )
    asyncio.run(client.run())


def main() -> None:
    cli()
