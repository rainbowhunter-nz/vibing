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
    DEFAULT_AGENT_CONTROL_PLANE_URL,
    DEFAULT_CONTROL_PLANE_URL,
    DEFAULT_DEVCONTAINER_CLI,
    WorkerConfig,
)

cli = typer.Typer(
    add_completion=False,
    help="Host Runtime Worker: drives Devcontainer lifecycle for the Control Plane.",
)


@cli.callback(invoke_without_command=True)
def serve(
    control_plane_url: str = typer.Option(
        DEFAULT_CONTROL_PLANE_URL, help="Control Plane runtime WebSocket URL (host uses 127.0.0.1)"
    ),
    devcontainer_cli: str = typer.Option(
        DEFAULT_DEVCONTAINER_CLI, help="Dev Container CLI binary name or path"
    ),
    agent_control_plane_url: str = typer.Option(
        DEFAULT_AGENT_CONTROL_PLANE_URL,
        help="Agent WebSocket URL injected into the container (uses host.docker.internal)",
    ),
) -> None:
    """Connect to the Control Plane, register, and run lifecycle Commands."""
    run_worker(
        WorkerConfig(
            control_plane_url=control_plane_url,
            devcontainer_cli=devcontainer_cli,
            agent_control_plane_url=agent_control_plane_url,
        )
    )


def run_worker(config: WorkerConfig) -> None:
    from vibing_host_runtime.agent_launcher import AgentLauncher
    from vibing_host_runtime.command_handler import DevcontainerCommandHandler
    from vibing_host_runtime.devcontainer_cli import DevcontainerCliAdapter

    logger.info(
        "Starting host runtime worker (control_plane=%s, devcontainer_cli=%s, agent_url=%s)",
        config.control_plane_url,
        config.devcontainer_cli,
        config.agent_control_plane_url,
    )
    adapter = DevcontainerCliAdapter(config.devcontainer_cli)
    launcher = AgentLauncher(
        devcontainer_cli=config.devcontainer_cli,
        agent_control_plane_url=config.agent_control_plane_url,
    )
    handler = DevcontainerCommandHandler(adapter, launcher=launcher)
    register = RegisterEnvelope(source="host_runtime_worker")
    client = RuntimeChannelClient(config.control_plane_url, register, handler.handle)
    asyncio.run(client.run())


def main() -> None:
    cli()
