"""Runtime WebSocket channel: host-worker and agent connections, plus event intake.

`ConnectionRegistry` holds keyed WebSocket slots; subclasses route a Command to its
slot. The Control Plane runs two: `WorkerRegistry` (the single host-worker slot,
ADR-0003: one worker per Control Plane) and `AgentRegistry` (per-devcontainer agents,
keyed by devcontainer_id). `persist_runtime_event` is the I/O seam that records an
inbound RuntimeEvent and projects it through the reducer — keeping SQL out of the route.
"""

import asyncio
import uuid
from abc import ABC, abstractmethod
from typing import Any

from fastapi import WebSocket
from vibing_protocol import (
    Command,
    CommandEnvelope,
    RuntimeEvent,
    TranscriptRequestEnvelope,
)

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
    """Routes each command to the agent registered for its devcontainer_id.

    Also runs the request/reply RPC for Session Transcripts (ADR-0009): a per-request
    `asyncio.Future` keyed by a Control-Plane-generated request_id, sent over the agent's
    WebSocket and awaited. request_id and turns are ephemeral — never persisted.
    """

    def __init__(self) -> None:
        super().__init__()
        self._inflight: dict[str, tuple[WebSocket, asyncio.Future[list[Any]]]] = {}

    def _slot_for(self, command: Command) -> str:
        return command.devcontainer_id or ""

    async def request_transcript(
        self, devcontainer_id: str, agent_session_id: str, timeout: float
    ) -> list[Any]:
        """Send a transcript_request to the agent and await its correlated reply."""
        ws = self._connections.get(devcontainer_id)
        if ws is None:
            raise RuntimeError(f"No agent connection registered for {devcontainer_id!r}")
        request_id = uuid.uuid4().hex
        future: asyncio.Future[list[Any]] = asyncio.get_running_loop().create_future()
        self._inflight[request_id] = (ws, future)
        try:
            await ws.send_json(
                TranscriptRequestEnvelope(
                    request_id=request_id, agent_session_id=agent_session_id
                ).model_dump()
            )
            return await asyncio.wait_for(future, timeout)
        finally:
            self._inflight.pop(request_id, None)

    def resolve_transcript(self, request_id: str, turns: list[Any]) -> None:
        """Resolve the matching in-flight Future. No-op if it is already gone."""
        entry = self._inflight.get(request_id)
        if entry is None:
            return
        _, future = entry
        if not future.done():
            future.set_result(turns)

    def unregister(self, key: str, websocket: WebSocket) -> None:
        super().unregister(key, websocket)
        self._fail_inflight_for(websocket)

    def _fail_inflight_for(self, websocket: WebSocket) -> None:
        """Reject every in-flight Future owned by a dropped connection so no awaiter hangs."""
        for request_id, (ws, future) in list(self._inflight.items()):
            if ws is websocket and not future.done():
                future.set_exception(ConnectionError("Agent connection dropped"))
                self._inflight.pop(request_id, None)


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
