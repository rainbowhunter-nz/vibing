"""Per-session live turn-delta fan-out (ADR-0010, VIB-109).

A SEPARATE channel from the global invalidation Broadcaster: subscribers are keyed by
agent_session_id and receive payload-bearing turn-deltas (the global /events stream
stays invalidation-only, ADR-0005/0006). LIVE-FROM-CONNECT — no replay buffer and no
Last-Event-ID reconnect (that is VIB-111). A subscriber that connects mid-run sees only
deltas published after it subscribed; the durable transcript remains the source of truth.

Thread-safe: publish() may be called from the WS intake; subscribe/unsubscribe run in
the async SSE request context.
"""

import queue


class SessionStreamRegistry:
    """Fan-out of turn-delta JSON payloads to browsers subscribed to one session."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[queue.SimpleQueue[str]]] = {}

    def subscribe(self, agent_session_id: str) -> "queue.SimpleQueue[str]":
        q: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._subscribers.setdefault(agent_session_id, []).append(q)
        return q

    def unsubscribe(self, agent_session_id: str, q: "queue.SimpleQueue[str]") -> None:
        subscribers = self._subscribers.get(agent_session_id)
        if subscribers is None:
            return
        try:
            subscribers.remove(q)
        except ValueError:
            pass
        if not subscribers:
            del self._subscribers[agent_session_id]

    def publish(self, agent_session_id: str, data: str) -> None:
        """Deliver a serialized turn-delta to every live subscriber of this session."""
        for q in list(self._subscribers.get(agent_session_id, [])):
            q.put(data)

    def subscriber_count(self, agent_session_id: str) -> int:
        return len(self._subscribers.get(agent_session_id, []))
