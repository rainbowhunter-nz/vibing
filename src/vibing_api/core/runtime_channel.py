"""Runtime WebSocket channel: host-worker and agent connections, plus event intake.

`RuntimeConnectionManager` tracks the one active Host Runtime Worker connection
(ADR-0003: one worker per Control Plane). `AgentConnectionManager` tracks per-devcontainer
agent connections keyed by devcontainer_id. `persist_runtime_event` is the I/O
seam that records an inbound RuntimeEvent and projects it through the reducer —
keeping SQL out of the route.
"""

from fastapi import WebSocket
from vibing_protocol import Command, CommandEnvelope, RuntimeEvent

from vibing_api.core.database import get_connection
from vibing_api.core.reducer import project
from vibing_api.repositories.runtime_events import RuntimeEventRepository


class RuntimeConnectionManager:
    """Holds the single active Host Runtime Worker connection."""

    def __init__(self) -> None:
        self._worker: WebSocket | None = None

    @property
    def worker(self) -> WebSocket | None:
        return self._worker

    def is_worker_connected(self) -> bool:
        return self._worker is not None

    def register_worker(self, websocket: WebSocket) -> bool:
        """Claim the single worker slot. Returns False if already taken."""
        if self._worker is not None:
            return False
        self._worker = websocket
        return True

    def unregister_worker(self, websocket: WebSocket) -> None:
        if self._worker is websocket:
            self._worker = None

    async def send_command(self, command: Command) -> None:
        """Send a Command to the connected worker. Raises if none is connected."""
        if self._worker is None:
            raise RuntimeError("No Host Runtime Worker is connected")
        await self._worker.send_json(CommandEnvelope(command=command).model_dump())


class AgentConnectionManager:
    """Tracks per-devcontainer Devcontainer Runtime Agent connections."""

    def __init__(self) -> None:
        self._agents: dict[str, WebSocket] = {}

    def is_agent_connected(self, devcontainer_id: str) -> bool:
        return devcontainer_id in self._agents

    def register_agent(self, devcontainer_id: str, websocket: WebSocket) -> bool:
        """Claim the slot for devcontainer_id. Returns False if already taken."""
        if devcontainer_id in self._agents:
            return False
        self._agents[devcontainer_id] = websocket
        return True

    def unregister_agent(self, devcontainer_id: str, websocket: WebSocket) -> None:
        if self._agents.get(devcontainer_id) is websocket:
            del self._agents[devcontainer_id]

    async def send_command(self, command: Command) -> None:
        """Route a Command to the agent for command.devcontainer_id. Raises if none connected."""
        ws = self._agents.get(command.devcontainer_id or "")
        if ws is None:
            raise RuntimeError(
                f"No Devcontainer Runtime Agent connected for {command.devcontainer_id!r}"
            )
        await ws.send_json(CommandEnvelope(command=command).model_dump())


def persist_runtime_event(event: RuntimeEvent) -> None:
    """Record an inbound RuntimeEvent and project it within one transaction."""
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
