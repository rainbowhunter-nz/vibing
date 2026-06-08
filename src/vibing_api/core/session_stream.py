"""Per-session live turn-delta fan-out with replay buffer (ADR-0010, VIB-111).

A SEPARATE channel from the global invalidation Broadcaster: subscribers are keyed by
agent_session_id and receive payload-bearing turn-deltas (the global /events stream
stays invalidation-only, ADR-0005/0006).

Replay buffer: each published chunk is stored as (event_id, data) with a monotonic
per-run integer counter (as a string, starting at "1"). On subscribe, the buffer is
snapshotted and the live queue is registered ATOMICALLY (under _lock), so no item is
ever missed or duplicated between the snapshot and queue registration.

Run lifecycle — explicit methods are preferred over parsing JSON in publish() so the
registry stays decoupled from the wire format, but publish() also parses the `kind`
field to auto-handle run_started and run_ended without requiring the relay to call
begin_run/end_run separately:
  - begin_run(session_id): clear buffer + reset counter (new run)
  - end_run(session_id):   evict buffer (terminal event; fresh connect finds nothing)
  - publish() auto-detects run_started → begin_run; run_ended → end_run after fan-out

Thread-safe: publish() may be called from the WS intake thread; subscribe/unsubscribe
run in the async SSE request context.
"""

import json
import queue
import threading


class SessionStreamRegistry:
    """Fan-out of turn-delta JSON payloads to browsers subscribed to one session.

    Each session has:
      - an in-memory replay buffer: list of (event_id: str, data: str)
      - a monotonic per-run integer counter (resets on begin_run)
      - a list of live subscriber queues that receive (event_id, data) on publish
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # per session: list of (event_id, data) for current run
        self._buffers: dict[str, list[tuple[str, str]]] = {}
        # per session: next event id counter (1-based, reset per run)
        self._counters: dict[str, int] = {}
        # per session: live subscriber queues receiving (event_id, data)
        self._subscribers: dict[str, list[queue.SimpleQueue[tuple[str, str]]]] = {}

    def begin_run(self, agent_session_id: str) -> None:
        """Start a new run: clear the buffer and reset the event id counter."""
        with self._lock:
            self._buffers[agent_session_id] = []
            self._counters[agent_session_id] = 1

    def end_run(self, agent_session_id: str) -> None:
        """Evict the buffer on terminal event; fresh connects find nothing to replay."""
        with self._lock:
            self._buffers.pop(agent_session_id, None)
            self._counters.pop(agent_session_id, None)

    def subscribe(
        self,
        agent_session_id: str,
        last_event_id: str | None = None,
    ) -> "tuple[list[tuple[str, str]], queue.SimpleQueue[tuple[str, str]]]":
        """Register a live queue and atomically snapshot the replay entries.

        Returns (replay, queue):
          - replay: buffer entries to emit first (all if last_event_id is None;
                    only entries with integer id > int(last_event_id) otherwise)
          - queue: live queue that receives (event_id, data) for future publishes

        The snapshot and registration happen under the same lock, so no published
        item is missed or duplicated in the gap between them.
        """
        q: queue.SimpleQueue[tuple[str, str]] = queue.SimpleQueue()
        with self._lock:
            self._subscribers.setdefault(agent_session_id, []).append(q)
            buf = self._buffers.get(agent_session_id, [])
            if last_event_id is None:
                replay = list(buf)
            else:
                after = int(last_event_id)
                replay = [(eid, data) for eid, data in buf if int(eid) > after]
        return replay, q

    def unsubscribe(
        self,
        agent_session_id: str,
        q: "queue.SimpleQueue[tuple[str, str]]",
    ) -> None:
        with self._lock:
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
        """Assign the next event id, append to buffer, and fan out to live subscribers.

        Also auto-detects run lifecycle from the `kind` field:
          - run_started → begin_run (clears old buffer, resets counter) before buffering
          - run_ended  → end_run (evicts buffer) after fan-out (so the delta is delivered)
        """
        kind = _parse_kind(data)

        # run_started resets everything before we buffer/fan-out the delta itself.
        if kind == "run_started":
            self.begin_run(agent_session_id)

        with self._lock:
            buf = self._buffers.get(agent_session_id)
            if buf is not None:
                event_id = str(self._counters[agent_session_id])
                self._counters[agent_session_id] += 1
                buf.append((event_id, data))
            else:
                # No active run buffer (before first begin_run or after eviction).
                # Still fan-out, but assign a transient id for the queue.
                event_id = "0"
            subs = list(self._subscribers.get(agent_session_id, []))

        for q in subs:
            q.put((event_id, data))

        # run_ended evicts after fan-out so subscribers still receive the terminal delta.
        if kind == "run_ended":
            self.end_run(agent_session_id)

    def subscriber_count(self, agent_session_id: str) -> int:
        with self._lock:
            return len(self._subscribers.get(agent_session_id, []))


def _parse_kind(data: str) -> str | None:
    """Extract the `kind` field from a serialized turn-delta JSON string."""
    try:
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            return parsed.get("kind")
    except (json.JSONDecodeError, AttributeError):
        pass
    return None
