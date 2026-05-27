import typer
from rich.console import Console
from rich.table import Table

from vibing_api.core.database import get_connection, init_db
from vibing_api.dev import sample_data as sd

dev_app = typer.Typer(help="Local development helpers.", no_args_is_help=True)
sample_data_app = typer.Typer(help="Manage local sample data.", no_args_is_help=True)
dev_app.add_typer(sample_data_app, name="sample_data")

console = Console()


@sample_data_app.command("seed")
def seed() -> None:
    """Insert the curated sample dataset."""
    init_db()
    with get_connection() as conn:
        inserted = sd.seed(conn)
        conn.commit()
    console.print(f"[green]Seeded {inserted} rows.[/green]")


@sample_data_app.command("reset")
def reset() -> None:
    """Remove all sample-prefixed rows."""
    init_db()
    with get_connection() as conn:
        removed = sd.reset(conn)
        conn.commit()
    console.print(f"[yellow]Removed {removed} sample rows.[/yellow]")


@sample_data_app.command("status")
def status() -> None:
    """Print per-table sample row counts."""
    init_db()
    with get_connection() as conn:
        counts = sd.status(conn)
    table = Table(title="Sample data")
    table.add_column("Table")
    table.add_column("Rows", justify="right")
    for name, count in counts.items():
        table.add_row(name, str(count))
    console.print(table)
