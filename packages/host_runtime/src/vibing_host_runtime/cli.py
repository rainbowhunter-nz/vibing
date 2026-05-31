"""Command-line entry point for the Host Runtime Worker.

A single flat Typer command that builds a `WorkerConfig` and runs the worker loop.
`run_worker` wires the Dev Container CLI adapter as the command handler and runs
`RuntimeChannelClient` from `vibing_runtime_client`.
"""

import asyncio

import typer
from logzero import logger
from vibing_protocol import RegisterEnvelope
from vibing_runtime_client import RuntimeChannelClient

from vibing_host_runtime.client import (
    DEFAULT_CONTROL_PLANE_URL,
    DEFAULT_DEVCONTAINER_CLI,
    WorkerConfig,
)

cli = typer.Typer(
    add_completion=False,
    help="Host Runtime Worker: drives Devcontainer lifecycle for the Control Plane.",
)


@cli.command()
def serve(
    control_plane_url: str = typer.Option(
        DEFAULT_CONTROL_PLANE_URL, help="Control Plane runtime WebSocket URL"
    ),
    devcontainer_cli: str = typer.Option(
        DEFAULT_DEVCONTAINER_CLI, help="Dev Container CLI binary name or path"
    ),
) -> None:
    """Connect to the Control Plane, register, and run lifecycle Commands."""
    run_worker(WorkerConfig(control_plane_url=control_plane_url, devcontainer_cli=devcontainer_cli))


def run_worker(config: WorkerConfig) -> None:
    from vibing_host_runtime.command_handler import DevcontainerCommandHandler
    from vibing_host_runtime.devcontainer_cli import DevcontainerCliAdapter

    logger.info(
        "Starting host runtime worker (control_plane=%s, devcontainer_cli=%s)",
        config.control_plane_url,
        config.devcontainer_cli,
    )
    adapter = DevcontainerCliAdapter(config.devcontainer_cli)
    handler = DevcontainerCommandHandler(adapter)
    register = RegisterEnvelope(source="host_runtime_worker")
    client = RuntimeChannelClient(config.control_plane_url, register, handler.handle)
    asyncio.run(client.run())


def main() -> None:
    cli()
