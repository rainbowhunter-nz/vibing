from typing import Annotated

import typer

from vibing_api.cli import dev_app
from vibing_cli import delegated
from vibing_cli.client import devcontainers, harnesses, http, system
from vibing_devcontainer_runtime.cli import cli as devcontainer_runtime_app
from vibing_devcontainer_runtime.preflight import preflight as runtime_preflight

app = typer.Typer(name="vibing", help="Vibing CLI.", no_args_is_help=True)


@app.callback()
def main(
    api_url: Annotated[
        str, typer.Option(envvar="VIBING_API_URL", help="Base URL of the Vibing API.")
    ] = http.DEFAULT_API_URL,
    api_prefix: Annotated[
        str, typer.Option(envvar="VIBING_API_V1_PREFIX", help="API version path prefix.")
    ] = http.DEFAULT_API_V1_PREFIX,
) -> None:
    """Vibing CLI."""
    http.configure(api_url, api_prefix)


app.add_typer(dev_app, name="dev")

runtime_app = typer.Typer(help="Run long-lived runtime workers.", no_args_is_help=True)
runtime_app.add_typer(devcontainer_runtime_app, name="devcontainer")
runtime_app.command("preflight")(runtime_preflight)
app.add_typer(runtime_app, name="runtime")

app.add_typer(delegated.app, name="delegated")
app.add_typer(devcontainers.app, name="devcontainer")
app.add_typer(harnesses.app, name="harness")
app.add_typer(system.app, name="system")
