import typer

from vibing_api.cli import dev_app
from vibing_devcontainer_runtime.cli import cli as devcontainer_runtime_app
from vibing_host_runtime.cli import cli as host_runtime_app

app = typer.Typer(name="vibing", help="Vibing CLI.", no_args_is_help=True)
app.add_typer(dev_app, name="dev")
app.add_typer(host_runtime_app, name="host-runtime")
app.add_typer(devcontainer_runtime_app, name="devcontainer-runtime")
