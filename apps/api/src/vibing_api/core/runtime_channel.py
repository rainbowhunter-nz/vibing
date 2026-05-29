"""Runtime WebSocket channel: the single host-worker connection and event intake.

`RuntimeConnectionManager` tracks the one active Host Runtime Worker connection
(ADR-0003: one worker per Control Plane). `persist_runtime_event` is the I/O
seam that records an inbound RuntimeEvent and projects it through the reducer —
keeping SQL out of the route.
"""

from fastapi import WebSocket
from vibing_protocol import RuntimeEvent

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

    def register_worker(self, websocket: WebSocket) -> bool:
        """Claim the single worker slot. Returns False if already taken."""
        if self._worker is not None:
            return False
        self._worker = websocket
        return True

    def unregister_worker(self, websocket: WebSocket) -> None:
        if self._worker is websocket:
            self._worker = None


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
