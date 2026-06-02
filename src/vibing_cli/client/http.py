from typing import Any

import httpx
import typer
from rich.console import Console

_err = Console(stderr=True)

DEFAULT_API_URL = "http://localhost:8080"
DEFAULT_API_V1_PREFIX = "/api/v1"

_base_url = f"{DEFAULT_API_URL}{DEFAULT_API_V1_PREFIX}"


def configure(api_url: str, api_prefix: str) -> None:
    """Set the API base URL. Called from the root CLI callback (resolves env vars)."""
    global _base_url
    _base_url = f"{api_url.rstrip('/')}{api_prefix}"


def base_url() -> str:
    return _base_url


def get_client() -> httpx.Client:
    return httpx.Client(base_url=base_url(), timeout=30.0)


def request(
    method: str,
    path: str,
    *,
    json: Any | None = None,
    params: dict[str, str] | None = None,
) -> Any:
    """Call the API and return parsed JSON (or None for empty/204). Exit 1 on failure."""
    try:
        with get_client() as client:
            response = client.request(method, path, json=json, params=params)
    except httpx.ConnectError:
        _err.print(f"[bold red]✗ Cannot reach API at {base_url()}[/bold red]")
        raise typer.Exit(1) from None

    if response.is_success:
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    _render_error(response)
    raise typer.Exit(1)


def _render_error(response: httpx.Response) -> None:
    try:
        error = response.json()["error"]
        _err.print(f"[bold red]✗ {error['code']}[/bold red]: {error['message']}")
    except (ValueError, KeyError, TypeError):
        _err.print(f"[bold red]✗ HTTP {response.status_code}[/bold red]: {response.text}")
