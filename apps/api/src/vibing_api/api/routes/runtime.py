"""Runtime WebSocket channel route (ADR-0003): runtime -> Control Plane intake.

A runtime connects, sends one `runtime_registered` envelope to claim the single
worker slot, then streams `runtime_event` envelopes. Malformed JSON, malformed
envelopes, and unsupported message types are ignored without producing events.
"""

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from vibing_protocol import RuntimeEventEnvelope

from vibing_api.core.runtime_channel import RuntimeConnectionManager, persist_runtime_event

router = APIRouter(tags=["runtime"], prefix="/runtime")

_WORKER_ALREADY_CONNECTED = 4409


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
