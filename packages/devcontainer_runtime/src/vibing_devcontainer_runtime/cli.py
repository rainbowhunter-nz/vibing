"""Command-line entry point for the Devcontainer Runtime Agent.

Connects to the Control Plane agent channel, registers with a devcontainer_id,
and idles awaiting Commands (session logic deferred to VIB-32).
"""

import asyncio

import typer
from logzero import logger
from vibing_protocol import Command, RegisterEnvelope
from vibing_runtime_client import RuntimeChannelClient

DEFAULT_CONTROL_PLANE_URL = "ws://host.docker.internal:8000/api/v1/runtime/agent/ws"

cli = typer.Typer(
    add_completion=False,
    help="Devcontainer Runtime Agent: connects to the Control Plane and idles awaiting Commands.",
)


@cli.command()
def serve(
    control_plane_url: str = typer.Option(
        DEFAULT_CONTROL_PLANE_URL, help="Control Plane agent WebSocket URL"
    ),
    devcontainer_id: str = typer.Option(..., help="Unique ID of this devcontainer"),
) -> None:
    """Connect to the Control Plane, register, and await Commands."""
    logger.info(
        "Starting devcontainer runtime agent (control_plane=%s, devcontainer_id=%s)",
        control_plane_url,
        devcontainer_id,
    )
    register = RegisterEnvelope(
        source="devcontainer_runtime_agent", devcontainer_id=devcontainer_id
    )

    async def handler(command: Command, emit: object) -> None:
        logger.info("Received command %s (devcontainer=%s)", command.type, command.devcontainer_id)

    client = RuntimeChannelClient(control_plane_url, register, handler)
    asyncio.run(client.run())


def main() -> None:
    cli()
