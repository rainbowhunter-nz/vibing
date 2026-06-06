"""Runtime WebSocket channel routes (ADR-0003): runtime -> Control Plane intake.

Two WebSocket endpoints, each backed by a `ConnectionRegistry`:
- `/runtime/ws` — host worker slot (single connection, WORKER_SLOT)
- `/runtime/agent/ws` — per-devcontainer agent slot (keyed by devcontainer_id)

Malformed JSON, malformed envelopes, and unsupported types are ignored.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from logzero import logger
from pydantic import ValidationError
from vibing_protocol import (
    RegisterEnvelope,
    RuntimeEventEnvelope,
    RuntimeEventSource,
    TranscriptResponseEnvelope,
)

from vibing_api.api.schemas.devcontainers import RuntimeStatus
from vibing_api.core.broadcaster import SseEvent
from vibing_api.core.runtime_channel import (
    WORKER_SLOT,
    AgentRegistry,
    WorkerRegistry,
    persist_runtime_event,
)

router = APIRouter(tags=["runtime"], prefix="/runtime")

_WORKER_ALREADY_CONNECTED = 4409
_AGENT_MISSING_ID = 4400
_AGENT_ALREADY_CONNECTED = 4409

# A register callback validates the `runtime_registered` message and claims a slot.
# Returns an unregister thunk on success, None to keep waiting (invalid envelope),
# or raises _Reject to close the connection with a code.
Register = Callable[[dict[str, Any]], Awaitable[Callable[[], None] | None]]


class _Reject(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


def _broadcast_connection(websocket: WebSocket, ids: list[str]) -> None:
    """Publish a runtime connection invalidation if a broadcaster is available."""
    broadcaster = getattr(websocket.app.state, "broadcaster", None)
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="runtime", ids=ids))


def _parse(raw: str) -> dict[str, Any] | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None


# Resolves a transcript_response onto its in-flight Future. Only the agent route
# supplies one; the worker route passes None, leaving transcript handling inert there.
ResolveTranscript = Callable[[str, list[Any]], None]


async def _serve(
    websocket: WebSocket,
    register: Register,
    resolve_transcript: ResolveTranscript | None = None,
) -> None:
    """Shared registration + RuntimeEvent intake loop for both runtime channels."""
    await websocket.accept()
    unregister: Callable[[], None] | None = None
    try:
        while True:
            message = _parse(await websocket.receive_text())
            if message is None:
                continue
            msg_type = message.get("type")

            if msg_type == "runtime_registered":
                if unregister is not None:
                    continue
                unregister = await register(message)
                if unregister is not None:
                    await websocket.send_json({"type": "registered"})
                continue

            if unregister is not None and msg_type == "transcript_response" and resolve_transcript:
                try:
                    response = TranscriptResponseEnvelope.model_validate(message)
                except ValidationError:
                    continue
                resolve_transcript(response.request_id, [t.model_dump() for t in response.turns])
                continue

            if unregister is None or msg_type != "runtime_event":
                continue

            try:
                envelope = RuntimeEventEnvelope.model_validate(message)
            except ValidationError:
                continue
            broadcaster = getattr(websocket.app.state, "broadcaster", None)
            try:
                persist_runtime_event(envelope.event, broadcaster)
            except Exception:
                logger.exception(
                    "Failed to persist runtime event %s (devcontainer=%s, session=%s)",
                    envelope.event.event_type,
                    envelope.event.devcontainer_id,
                    envelope.event.agent_session_id,
                )
    except WebSocketDisconnect:
        pass
    except _Reject as reject:
        await websocket.close(code=reject.code)
    finally:
        if unregister is not None:
            unregister()


@router.get("/status", response_model=RuntimeStatus)
def get_runtime_status(request: Request) -> RuntimeStatus:
    manager: WorkerRegistry = request.app.state.runtime_manager
    return RuntimeStatus(worker_connected=manager.is_connected(WORKER_SLOT))


@router.websocket("/ws")
async def runtime_ws(websocket: WebSocket) -> None:
    manager: WorkerRegistry = websocket.app.state.runtime_manager

    async def register(message: dict[str, Any]) -> Callable[[], None] | None:
        try:
            RegisterEnvelope.model_validate(message)
        except ValidationError:
            return None
        if not manager.register(WORKER_SLOT, websocket):
            raise _Reject(_WORKER_ALREADY_CONNECTED)
        _broadcast_connection(websocket, ids=[])

        def unregister() -> None:
            manager.unregister(WORKER_SLOT, websocket)
            _broadcast_connection(websocket, ids=[])

        return unregister

    await _serve(websocket, register)


@router.websocket("/agent/ws")
async def agent_ws(websocket: WebSocket) -> None:
    manager: AgentRegistry = websocket.app.state.agent_manager

    async def register(message: dict[str, Any]) -> Callable[[], None] | None:
        try:
            envelope = RegisterEnvelope.model_validate(message)
        except ValidationError:
            return None
        if (
            envelope.source != RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT
            or not envelope.devcontainer_id
        ):
            raise _Reject(_AGENT_MISSING_ID)
        if not manager.register(envelope.devcontainer_id, websocket):
            raise _Reject(_AGENT_ALREADY_CONNECTED)
        devcontainer_id = envelope.devcontainer_id
        _broadcast_connection(websocket, ids=[devcontainer_id])

        def unregister() -> None:
            manager.unregister(devcontainer_id, websocket)
            _broadcast_connection(websocket, ids=[devcontainer_id])

        return unregister

    await _serve(websocket, register, resolve_transcript=manager.resolve_transcript)
