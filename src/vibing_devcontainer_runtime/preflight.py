"""In-container preflight: probe the Control Plane health endpoint before spawning.

Runs after bootstrap (vibing is installed). GETs the HTTP health endpoint derived from
the same resolved WS URL the runtime will connect to, so a wrong resolved URL fails here
instead of after a silent spawn. Failure leaves a clear line in the unified log.
"""

import urllib.error
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

import typer

_WS_TO_HTTP = {"ws": "http", "wss": "https"}
_RUNTIME_PATH_SUFFIX = "/runtime/agent/ws"
_HEALTH_PATH = "/health"


def health_url_from_ws(ws_url: str) -> str:
    parsed = urlparse(ws_url)
    scheme = _WS_TO_HTTP.get(parsed.scheme, parsed.scheme)
    path = parsed.path
    if path.endswith(_RUNTIME_PATH_SUFFIX):
        path = path[: -len(_RUNTIME_PATH_SUFFIX)] + _HEALTH_PATH
    else:
        path = _HEALTH_PATH
    return urlunparse(parsed._replace(scheme=scheme, path=path))


def check_reachable(ws_url: str, timeout: float = 5.0) -> tuple[bool, str]:
    health = health_url_from_ws(ws_url)
    try:
        with urlopen(health, timeout=timeout) as resp:
            if resp.status == 200:
                return True, f"preflight ok: control plane reachable at {health}"
            return (
                False,
                f"PREFLIGHT FAILED: control plane unreachable at {health}: HTTP {resp.status}",
            )
    except (urllib.error.URLError, OSError) as exc:
        return False, f"PREFLIGHT FAILED: control plane unreachable at {health}: {exc}"


def preflight(
    control_plane_url: str = typer.Option(..., help="Control Plane WS URL"),
) -> None:
    """Exit 0 if the Control Plane health endpoint is reachable, else exit 1."""
    ok, message = check_reachable(control_plane_url)
    if ok:
        typer.echo(message)
        raise typer.Exit(0)
    typer.echo(message, err=True)
    raise typer.Exit(1)
