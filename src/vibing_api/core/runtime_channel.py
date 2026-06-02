"""Runtime WebSocket channel: host-worker and agent connections, plus event intake.

`ConnectionRegistry` holds keyed WebSocket slots; subclasses route a Command to its
slot. The Control Plane runs two: `WorkerRegistry` (the single host-worker slot,
ADR-0003: one worker per Control Plane) and `AgentRegistry` (per-devcontainer agents,
keyed by devcontainer_id). `persist_runtime_event` is the I/O seam that records an
inbound RuntimeEvent and projects it through the reducer — keeping SQL out of the route.
"""

from abc import ABC, abstractmethod

from fastapi import WebSocket
from vibing_protocol import Command, CommandEnvelope, RuntimeEvent

from vibing_api.core.broadcaster import Broadcaster
from vibing_api.core.database import get_connection
from vibing_api.core.reducer import invalidations_for, project
from vibing_api.repositories.runtime_events import RuntimeEventRepository


WORKER_SLOT = "worker"


class ConnectionRegistry(ABC):
    """Keyed WebSocket slots: single-claim register, identity-checked release, send.

    Subclasses implement `_slot_for` to route a Command to its slot.
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    def is_connected(self, key: str) -> bool:
        return key in self._connections

    def register(self, key: str, websocket: WebSocket) -> bool:
        """Claim the slot for key. Returns False if already taken."""
        if key in self._connections:
            return False
        self._connections[key] = websocket
        return True

    def unregister(self, key: str, websocket: WebSocket) -> None:
        if self._connections.get(key) is websocket:
            del self._connections[key]

    @abstractmethod
    def _slot_for(self, command: Command) -> str: ...

    async def send_command(self, command: Command) -> None:
        slot = self._slot_for(command)
        ws = self._connections.get(slot)
        if ws is None:
            raise RuntimeError(f"No runtime connection registered for {slot!r}")
        await ws.send_json(CommandEnvelope(command=command).model_dump())


class WorkerRegistry(ConnectionRegistry):
    """Routes every command to the single host-worker slot (ADR-0003)."""

    def _slot_for(self, command: Command) -> str:
        return WORKER_SLOT


class AgentRegistry(ConnectionRegistry):
    """Routes each command to the agent registered for its devcontainer_id."""

    def _slot_for(self, command: Command) -> str:
        return command.devcontainer_id or ""


def persist_runtime_event(event: RuntimeEvent, broadcaster: Broadcaster | None = None) -> None:
    """Record an inbound RuntimeEvent, project it, commit, then broadcast invalidations."""
    with get_connection() as conn:
        recorded = RuntimeEventRepository(conn).record(
            event_type=event.event_type,
            source=event.source,
            devcontainer_id=event.devcontainer_id,
            agent_session_id=event.agent_session_id,
            payload=event.payload,
        )
        project(recorded, conn)
        conn.commit()
    if broadcaster is not None:
        for sse_event in invalidations_for(recorded):
            broadcaster.publish(sse_event)
