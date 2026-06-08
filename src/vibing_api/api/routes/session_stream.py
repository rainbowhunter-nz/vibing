"""Per-session live turn-delta SSE: GET .../agent-sessions/{id}/stream (ADR-0010, VIB-111).

A SEPARATE endpoint from the global invalidation /events stream (which stays
payload-free, ADR-0005/0006). Browsers subscribe here while a session is active to
receive token-by-token assistant text.

Replay + reconnect (VIB-111):
  - On connect, replay the current run's buffered events (full run if no Last-Event-ID;
    only events after Last-Event-ID on reconnect), then stream live.
  - Every SSE event carries an `id:` field so browsers track lastEventId automatically.
  - The durable transcript stays the source of truth; the browser reconciles to it on
    the terminal run_ended delta.
"""

import asyncio
import queue
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from vibing_api.core.session_stream import SessionStreamRegistry

router = APIRouter(tags=["session-stream"], prefix="/devcontainers")

_POLL_INTERVAL = 0.05  # seconds between queue polls


async def _stream_generator(
    registry: SessionStreamRegistry,
    agent_session_id: str,
    request: Request,
    max_events: int | None,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Yield turn-delta SSE events for one session until the client disconnects.

    Emits replayed entries first (each with its buffered id), then streams live
    events from the queue. Every event carries an `id:` field.
    """
    if max_events is not None and max_events <= 0:
        return

    last_event_id = request.headers.get("last-event-id") or None
    replay, q = registry.subscribe(agent_session_id, last_event_id=last_event_id)
    emitted = 0
    try:
        # Emit buffered replay entries first.
        for event_id, data in replay:
            yield ServerSentEvent(raw_data=data, id=event_id, event="turn_delta")
            emitted += 1
            if max_events is not None and emitted >= max_events:
                return

        # Stream live events from the queue.
        while True:
            if await request.is_disconnected():
                break
            try:
                event_id, data = q.get_nowait()
                yield ServerSentEvent(raw_data=data, id=event_id, event="turn_delta")
                emitted += 1
                if max_events is not None and emitted >= max_events:
                    break
            except queue.Empty:
                await asyncio.sleep(_POLL_INTERVAL)
    finally:
        registry.unsubscribe(agent_session_id, q)


@router.get(
    "/{devcontainer_id}/agent-sessions/{agent_session_id}/stream",
    response_class=EventSourceResponse,
)
async def session_stream(
    devcontainer_id: str,
    agent_session_id: str,
    request: Request,
    max_events: int | None = Query(default=None, alias="_max"),
) -> AsyncGenerator[ServerSentEvent, None]:
    """Live turn-delta stream for one active session. Replays current run on connect."""
    registry: SessionStreamRegistry = request.app.state.session_streams
    async for item in _stream_generator(registry, agent_session_id, request, max_events):
        yield item
