import typer

from vibing_api.cli.dev import dev_app

app = typer.Typer(name="vibing", help="Vibing local development CLI.", no_args_is_help=True)
app.add_typer(dev_app, name="dev")
