"""Per-devcontainer runtime connection registry (liveness/intake only; outbound-only channel)."""

from typing import Protocol

from fastapi import WebSocket


class RuntimeConnection(Protocol):
    """A live link to one Devcontainer Runtime."""


class WebSocketRuntimeConnection:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket


class RuntimeRegistry:
    def __init__(self) -> None:
        self._connections: dict[str, RuntimeConnection] = {}

    def is_connected(self, devcontainer_id: str) -> bool:
        return devcontainer_id in self._connections

    def register(self, devcontainer_id: str, connection: RuntimeConnection) -> bool:
        if devcontainer_id in self._connections:
            return False
        self._connections[devcontainer_id] = connection
        return True

    def unregister(self, devcontainer_id: str, connection: RuntimeConnection) -> None:
        if self._connections.get(devcontainer_id) is connection:
            del self._connections[devcontainer_id]
