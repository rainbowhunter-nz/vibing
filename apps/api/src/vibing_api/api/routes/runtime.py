"""Runtime WebSocket channel routes (ADR-0003): runtime -> Control Plane intake.

Two WebSocket endpoints:
- `/runtime/ws` — host worker slot (single connection, RuntimeConnectionManager)
- `/runtime/agent/ws` — per-devcontainer agent slot (AgentConnectionManager, keyed by devcontainer_id)

Malformed JSON, malformed envelopes, and unsupported types are ignored.
"""

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from vibing_protocol import RegisterEnvelope, RuntimeEventEnvelope

from vibing_api.core.runtime_channel import (
    AgentConnectionManager,
    RuntimeConnectionManager,
    persist_runtime_event,
)

router = APIRouter(tags=["runtime"], prefix="/runtime")

_WORKER_ALREADY_CONNECTED = 4409
_AGENT_MISSING_ID = 4400
_AGENT_ALREADY_CONNECTED = 4409


def _parse(raw: str) -> dict[str, Any] | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None


@router.websocket("/ws")
async def runtime_ws(websocket: WebSocket) -> None:
    manager: RuntimeConnectionManager = websocket.app.state.runtime_manager
    await websocket.accept()
    registered = False
    try:
        while True:
            message = _parse(await websocket.receive_text())
            if message is None:
                continue
            msg_type = message.get("type")

            if msg_type == "runtime_registered":
                if registered:
                    continue
                try:
                    RegisterEnvelope.model_validate(message)
                except ValidationError:
                    continue
                if not manager.register_worker(websocket):
                    await websocket.close(code=_WORKER_ALREADY_CONNECTED)
                    return
                registered = True
                await websocket.send_json({"type": "registered"})
                continue

            if not registered or msg_type != "runtime_event":
                continue

            try:
                envelope = RuntimeEventEnvelope.model_validate(message)
            except ValidationError:
                continue
            persist_runtime_event(envelope.event)
    except WebSocketDisconnect:
        pass
    finally:
        if registered:
            manager.unregister_worker(websocket)


@router.websocket("/agent/ws")
async def agent_ws(websocket: WebSocket) -> None:
    manager: AgentConnectionManager = websocket.app.state.agent_manager
    await websocket.accept()
    registered = False
    devcontainer_id: str | None = None
    try:
        while True:
            message = _parse(await websocket.receive_text())
            if message is None:
                continue
            msg_type = message.get("type")

            if msg_type == "runtime_registered":
                if registered:
                    continue
                try:
                    envelope = RegisterEnvelope.model_validate(message)
                except ValidationError:
                    continue
                if envelope.source != "devcontainer_runtime_agent" or not envelope.devcontainer_id:
                    await websocket.close(code=_AGENT_MISSING_ID)
                    return
                if not manager.register_agent(envelope.devcontainer_id, websocket):
                    await websocket.close(code=_AGENT_ALREADY_CONNECTED)
                    return
                devcontainer_id = envelope.devcontainer_id
                registered = True
                await websocket.send_json({"type": "registered"})
                continue

            if not registered or msg_type != "runtime_event":
                continue

            try:
                env = RuntimeEventEnvelope.model_validate(message)
            except ValidationError:
                continue
            persist_runtime_event(env.event)
    except WebSocketDisconnect:
        pass
    finally:
        if registered and devcontainer_id is not None:
            manager.unregister_agent(devcontainer_id, websocket)
