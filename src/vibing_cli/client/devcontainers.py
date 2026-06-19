from typing import Annotated

import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, console, render

app = typer.Typer(help="Manage devcontainers via the API.", no_args_is_help=True)

_BASE = "/devcontainers"


@app.command("add")
def add(
    name: str,
    local_path: Annotated[str, typer.Option("-d", "--local-path", help="Local project path.")],
    json_: JsonOption = False,
) -> None:
    """Create a devcontainer."""
    render(request("POST", _BASE, json={"name": name, "local_path": local_path}), json_)


@app.command("ls")
def ls(json_: JsonOption = False) -> None:
    """List devcontainers."""
    render(request("GET", _BASE), json_)


@app.command("get")
def get(devcontainer_id: str, json_: JsonOption = False) -> None:
    """Show one devcontainer."""
    render(request("GET", f"{_BASE}/{devcontainer_id}"), json_)


@app.command("update")
def update(
    devcontainer_id: str,
    name: Annotated[str | None, typer.Option("--name")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    json_: JsonOption = False,
) -> None:
    """Update a devcontainer's name or status."""
    body = {
        key: value for key, value in {"name": name, "status": status}.items() if value is not None
    }
    if not body:
        typer.echo("Specify at least one of --name or --status.", err=True)
        raise typer.Exit(1)
    render(request("PATCH", f"{_BASE}/{devcontainer_id}", json=body), json_)


@app.command("rm")
def rm(devcontainer_id: str) -> None:
    """Delete a devcontainer."""
    request("DELETE", f"{_BASE}/{devcontainer_id}")
    console.print(f"[green]✓ Deleted {devcontainer_id}.[/green]")


@app.command("start")
def start(devcontainer_id: str, json_: JsonOption = False) -> None:
    """Start a devcontainer."""
    render(request("POST", f"{_BASE}/{devcontainer_id}/start"), json_)


@app.command("stop")
def stop(devcontainer_id: str, json_: JsonOption = False) -> None:
    """Stop a devcontainer."""
    render(request("POST", f"{_BASE}/{devcontainer_id}/stop"), json_)
