import json as _json
from datetime import datetime
from typing import Annotated, Any

import typer
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

JsonOption = Annotated[bool, typer.Option("--json", help="Raw JSON output.")]

_STATUS_STYLES = {
    "running": "bold green",
    "active": "bold green",
    "ready": "bold green",
    "online": "bold green",
    "healthy": "bold green",
    "ok": "green",
    "completed": "green",
    "succeeded": "green",
    "resolved": "green",
    "approved": "green",
    "pending": "yellow",
    "starting": "yellow",
    "stopping": "yellow",
    "queued": "yellow",
    "waiting": "yellow",
    "in_progress": "yellow",
    "stopped": "dim",
    "inactive": "dim",
    "idle": "dim",
    "offline": "dim",
    "error": "bold red",
    "failed": "bold red",
    "rejected": "bold red",
    "unhealthy": "bold red",
}


def render(data: Any, as_json: bool) -> None:
    if as_json:
        console.print_json(_json.dumps(data))
        return
    if data is None:
        return
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        _render_list(data["items"])
    elif isinstance(data, list):
        _render_list(data)
    else:
        _render_object(data)


def _render_list(items: list[dict[str, Any]]) -> None:
    if not items:
        console.print("[dim]No results.[/dim]")
        return
    columns = list(items[0].keys())
    table = _new_table()
    for column in columns:
        table.add_column(column)
    for item in items:
        table.add_row(*(_cell(column, item.get(column)) for column in columns))
    console.print(table)


def _render_object(obj: dict[str, Any]) -> None:
    table = _new_table(show_header=False)
    table.add_column("field", style="bold cyan", justify="right")
    table.add_column("value")
    for key, value in obj.items():
        table.add_row(key, _cell(key, value))
    console.print(table)


def _new_table(show_header: bool = True) -> Table:
    return Table(
        box=box.ROUNDED,
        header_style="bold cyan",
        border_style="bright_black",
        show_header=show_header,
        expand=False,
    )


def _cell(column: str, value: Any) -> Text:
    """Render one value as styled rich Text based on its column and content."""
    if value is None or value == "":
        return Text("—", style="dim")
    if isinstance(value, bool):
        return Text("true" if value else "false", style="green" if value else "red")
    text = str(value)
    key = column.lower()
    if "status" in key or "state" in key:
        return Text(text, style=_STATUS_STYLES.get(text.lower(), "white"))
    if key == "id" or key.endswith("_id"):
        return Text(text, style="cyan")
    if key.endswith(("_at", "_time")) or key in {"created", "updated"}:
        return Text(_format_time(text), style="dim")
    return Text(text)


def _format_time(text: str) -> str:
    """Format an ISO timestamp in local time as '02 Jun 06:00:00 am'; pass through if unparsable."""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return text
    return dt.strftime("%d %b %I:%M:%S %p").replace("AM", "am").replace("PM", "pm")
