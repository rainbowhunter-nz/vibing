"""In-memory SSE broadcaster: publish invalidation events to all subscribed browser clients.

Downstream tickets (VIB-45, VIB-46) call `broadcaster.publish(SseEvent(...))` to notify
clients to refetch canonical HTTP data. No payload data is sent — only scope + ids.

Scopes: devcontainers | agent_sessions | inbox | approvals | runtime

Thread-safe: publish() may be called from any thread. subscribe/unsubscribe are
called from the async request context (FastAPI route coroutines).
"""

import queue
from dataclasses import dataclass
from typing import Literal


Scope = Literal["devcontainers", "agent_sessions", "inbox", "approvals", "runtime"]


@dataclass(frozen=True)
class SseEvent:
    scope: Scope
    ids: list[str]
    event_type: str = "invalidate"


class Broadcaster:
    """Fan-out: one publish reaches every subscribed SSE response generator.

    Subscribers hold a `queue.SimpleQueue[SseEvent]` (thread-safe). The SSE
    generator polls the queue with `get_nowait()` inside an async sleep loop.
    """

    def __init__(self) -> None:
        self._queues: list[queue.SimpleQueue[SseEvent]] = []

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    def subscribe(self) -> "queue.SimpleQueue[SseEvent]":
        """Register a new subscriber. Called from the async request handler."""
        q: queue.SimpleQueue[SseEvent] = queue.SimpleQueue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: "queue.SimpleQueue[SseEvent]") -> None:
        """Remove a subscriber. Called from the async request handler."""
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    def publish(self, event: SseEvent) -> None:
        """Deliver an event to all current subscribers. Thread-safe."""
        for q in list(self._queues):
            q.put(event)
