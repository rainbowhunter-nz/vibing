"""Per-session live turn-delta SSE: GET .../agent-sessions/{id}/stream (ADR-0010).

A SEPARATE endpoint from the global invalidation /events stream (which stays
payload-free, ADR-0005/0006). Browsers subscribe here while a session is active to
receive token-by-token assistant text. LIVE-FROM-CONNECT — no replay buffer, no
Last-Event-ID reconnect (VIB-111). The durable transcript stays the source of truth;
the browser reconciles to it on the terminal `run_ended` delta.
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
    """Yield turn-delta SSE events for one session until the client disconnects."""
    if max_events is not None and max_events <= 0:
        return
    q = registry.subscribe(agent_session_id)
    emitted = 0
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                data = q.get_nowait()
                yield ServerSentEvent(raw_data=data, event="turn_delta")
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
    """Live turn-delta stream for one active session. Empty when the session is resting."""
    registry: SessionStreamRegistry = request.app.state.session_streams
    async for item in _stream_generator(registry, agent_session_id, request, max_events):
        yield item
