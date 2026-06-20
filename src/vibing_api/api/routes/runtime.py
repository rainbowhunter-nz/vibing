"""Runtime WebSocket channel routes (ADR-0003, ADR-0014/0015): runtime -> Control Plane intake.

Single WebSocket endpoint `/runtime/agent/ws` — per-devcontainer agent slot keyed by devcontainer_id.
Inbound types: `runtime_registered` (registration), `harness_status` (status update).
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from logzero import logger
from pydantic import ValidationError
from vibing_protocol import DelegatedRunsEnvelope, HarnessStatusEnvelope, RegisterEnvelope

from vibing_api.core.broadcaster import SseEvent
from vibing_api.core.runtime_channel import (
    RuntimeRegistry,
    WebSocketRuntimeConnection,
    persist_delegated_runs,
    persist_harness_status,
)

router = APIRouter(tags=["runtime"], prefix="/runtime")

_AGENT_MISSING_ID = 4400
_AGENT_ALREADY_CONNECTED = 4409

Register = Callable[[dict[str, Any]], Awaitable[Callable[[], None] | None]]


class _Reject(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


def _broadcast_connection(websocket: WebSocket, ids: list[str]) -> None:
    broadcaster = getattr(websocket.app.state, "broadcaster", None)
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="runtime", ids=ids))


def _parse(raw: str) -> dict[str, Any] | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None


async def _serve(websocket: WebSocket, register: Register) -> None:
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

            if unregister is None:
                continue

            if msg_type == "harness_status":
                try:
                    envelope = HarnessStatusEnvelope.model_validate(message)
                except ValidationError:
                    continue
                broadcaster = getattr(websocket.app.state, "broadcaster", None)
                try:
                    persist_harness_status(envelope.devcontainer_id, envelope.items, broadcaster)
                except Exception:
                    logger.exception(
                        "Failed to persist harness status (devcontainer=%s)",
                        envelope.devcontainer_id,
                    )
                continue

            if msg_type == "delegated_runs":
                try:
                    runs_env = DelegatedRunsEnvelope.model_validate(message)
                except ValidationError:
                    continue
                broadcaster = getattr(websocket.app.state, "broadcaster", None)
                try:
                    persist_delegated_runs(runs_env.devcontainer_id, runs_env.items, broadcaster)
                except Exception:
                    logger.exception(
                        "Failed to persist delegated runs (devcontainer=%s)",
                        runs_env.devcontainer_id,
                    )
                continue
    except WebSocketDisconnect:
        pass
    except _Reject as reject:
        await websocket.close(code=reject.code)
    finally:
        if unregister is not None:
            unregister()


@router.websocket("/agent/ws")
async def agent_ws(websocket: WebSocket) -> None:
    manager: RuntimeRegistry = websocket.app.state.runtime_manager

    async def register(message: dict[str, Any]) -> Callable[[], None] | None:
        try:
            envelope = RegisterEnvelope.model_validate(message)
        except ValidationError:
            return None
        if not envelope.devcontainer_id:
            raise _Reject(_AGENT_MISSING_ID)
        connection = WebSocketRuntimeConnection(websocket)
        if not manager.register(envelope.devcontainer_id, connection):
            raise _Reject(_AGENT_ALREADY_CONNECTED)
        devcontainer_id = envelope.devcontainer_id
        _broadcast_connection(websocket, ids=[devcontainer_id])

        def unregister() -> None:
            manager.unregister(devcontainer_id, connection)
            _broadcast_connection(websocket, ids=[devcontainer_id])

        return unregister

    await _serve(websocket, register)
