import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, render

app = typer.Typer(help="Read control-plane status endpoints.", no_args_is_help=True)


@app.command("status")
def status(json_: JsonOption = False) -> None:
    """Show control-plane status."""
    render(request("GET", "/status"), json_)


@app.command("diagnostics")
def diagnostics(json_: JsonOption = False) -> None:
    """Show diagnostics."""
    render(request("GET", "/diagnostics"), json_)


@app.command("config")
def config(json_: JsonOption = False) -> None:
    """Show runtime config."""
    render(request("GET", "/config"), json_)


@app.command("settings")
def settings(json_: JsonOption = False) -> None:
    """Show settings."""
    render(request("GET", "/settings"), json_)


@app.command("health")
def health(json_: JsonOption = False) -> None:
    """Show health."""
    render(request("GET", "/health"), json_)
