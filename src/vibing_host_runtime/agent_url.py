"""Resolve agent control-plane URLs for sibling devcontainers.

host.docker.internal often maps to a host-gateway address that cannot reach a
control-plane container published on a bridge network (common on Podman/Linux).
When the host worker runs alongside uvicorn, substitute the container's own IP.
"""

import socket
from urllib.parse import urlparse, urlunparse

_HOST_ALIASES = frozenset({"host.docker.internal", "host.containers.internal"})


def _container_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


def resolve_agent_control_plane_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname not in _HOST_ALIASES:
        return url
    ip = _container_ip()
    if not ip:
        return url
    netloc = f"{ip}:{parsed.port}" if parsed.port else ip
    return urlunparse(parsed._replace(netloc=netloc))
