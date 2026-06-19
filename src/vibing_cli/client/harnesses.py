import json
from typing import Annotated

import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, console, render

app = typer.Typer(help="Manage coding harnesses via the API.", no_args_is_help=True)
creds_app = typer.Typer(help="Manage harness credentials.", no_args_is_help=True)
app.add_typer(creds_app, name="creds")

_DC_BASE = "/devcontainers"
_SETTINGS_BASE = "/settings"


@app.command("ls")
def ls(devcontainer_id: str, json_: JsonOption = False) -> None:
    """List harnesses for a devcontainer."""
    render(request("GET", f"{_DC_BASE}/{devcontainer_id}/harnesses"), json_)


@app.command("authenticate")
def authenticate(devcontainer_id: str, name: str, json_: JsonOption = False) -> None:
    """Trigger harness authentication."""
    render(
        request("POST", f"{_DC_BASE}/{devcontainer_id}/harnesses/{name}/authenticate"),
        json_,
    )


@creds_app.command("set")
def creds_set(
    name: str,
    blob: Annotated[str, typer.Option("--blob", help="Credentials JSON blob.")],
    json_: JsonOption = False,
) -> None:
    """Set harness credentials."""
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON blob: {exc}", err=True)
        raise typer.Exit(1) from exc

    render(
        request("PUT", f"{_SETTINGS_BASE}/harness-credentials/{name}", json={"blob": parsed}), json_
    )
    if not json_:
        console.print(f"[green]✓ Credentials set for {name}.[/green]")
