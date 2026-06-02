"""SSE endpoint: GET /api/v1/events

Browser clients subscribe here for lightweight invalidation events.
They MUST refetch canonical HTTP endpoints on receipt — no payload data is sent.

FastAPI's native EventSourceResponse handles keepalive pings (default 15 s, patchable
via `fastapi.sse._PING_INTERVAL`) and structured cancellation on client disconnect.

Scopes: devcontainers | agent_sessions | inbox | approvals | runtime
"""

import asyncio
import json
import queue
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from vibing_api.core.broadcaster import Broadcaster, SseEvent


router = APIRouter(tags=["events"])

_POLL_INTERVAL = 0.05  # seconds between queue polls


async def _sse_generator(
    broadcaster: Broadcaster,
    request: Request,
    max_events: int | None,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Yield SSE events from the broadcaster until client disconnects.

    max_events: stop after emitting this many events (tests only; None = infinite).
    """
    if max_events is not None and max_events <= 0:
        return  # nothing to emit
    q = broadcaster.subscribe()
    emitted = 0
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event: SseEvent = q.get_nowait()
                data = json.dumps(
                    {"event_type": event.event_type, "scope": event.scope, "ids": event.ids}
                )
                yield ServerSentEvent(raw_data=data, event=event.event_type)
                emitted += 1
                if max_events is not None and emitted >= max_events:
                    break
            except queue.Empty:
                await asyncio.sleep(_POLL_INTERVAL)
    finally:
        broadcaster.unsubscribe(q)


@router.get("/events", response_class=EventSourceResponse)
async def sse_events(
    request: Request,
    max_events: int | None = Query(default=None, alias="_max"),
) -> AsyncGenerator[ServerSentEvent, None]:
    """SSE invalidation stream. Clients refetch canonical HTTP data on each event."""
    broadcaster: Broadcaster = request.app.state.broadcaster
    async for item in _sse_generator(broadcaster, request, max_events):
        yield item
