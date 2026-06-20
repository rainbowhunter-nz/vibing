"""Per-devcontainer runtime connection registry."""

from typing import Protocol

from fastapi import WebSocket
from vibing_protocol import Command, CommandEnvelope, encode


class RuntimeConnection(Protocol):
    """A live link to one Devcontainer Runtime, able to receive Commands."""

    async def send(self, command: Command) -> None: ...


class WebSocketRuntimeConnection:
    """RuntimeConnection over the runtime's WebSocket; owns the wire format."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket

    async def send(self, command: Command) -> None:
        await self._websocket.send_text(encode(CommandEnvelope(command=command)))


class RuntimeRegistry:
    """Keyed runtime connections, one per devcontainer_id."""

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

    async def send_command(self, devcontainer_id: str, command: Command) -> None:
        connection = self._connections.get(devcontainer_id)
        if connection is None:
            raise RuntimeError(f"No runtime connection for {devcontainer_id!r}")
        await connection.send(command)
