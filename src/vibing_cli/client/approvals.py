import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, render

app = typer.Typer(help="Inspect approval requests via the API.", no_args_is_help=True)

_BASE = "/approval-requests"


@app.command("ls")
def ls(json_: JsonOption = False) -> None:
    """List approval requests."""
    render(request("GET", _BASE), json_)


@app.command("get")
def get(approval_request_id: str, json_: JsonOption = False) -> None:
    """Show one approval request."""
    render(request("GET", f"{_BASE}/{approval_request_id}"), json_)
