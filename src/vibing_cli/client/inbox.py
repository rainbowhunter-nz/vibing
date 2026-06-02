from typing import Annotated

import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, render

app = typer.Typer(help="Inspect inbox events via the API.", no_args_is_help=True)

_BASE = "/inbox-events"


@app.command("ls")
def ls(
    status: Annotated[str | None, typer.Option("--status")] = None,
    devcontainer: Annotated[str | None, typer.Option("--devcontainer")] = None,
    session: Annotated[str | None, typer.Option("--session")] = None,
    json_: JsonOption = False,
) -> None:
    """List inbox events, optionally filtered."""
    params = {
        key: value
        for key, value in {
            "status": status,
            "devcontainer_id": devcontainer,
            "agent_session_id": session,
        }.items()
        if value is not None
    }
    render(request("GET", _BASE, params=params), json_)


@app.command("get")
def get(inbox_event_id: str, json_: JsonOption = False) -> None:
    """Show one inbox event with detail."""
    render(request("GET", f"{_BASE}/{inbox_event_id}"), json_)
