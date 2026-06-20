"""Unit tests for the WebSocketRuntimeConnection adapter in runtime_channel."""

import asyncio
import json
from unittest.mock import AsyncMock

from vibing_api.core.runtime_channel import WebSocketRuntimeConnection
from vibing_protocol import Command, CommandEnvelope, CommandType


def test_websocket_runtime_connection_sends_command_envelope() -> None:
    websocket = AsyncMock()
    connection = WebSocketRuntimeConnection(websocket)
    command = Command(
        type=CommandType.INSTALL_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex"},
    )

    asyncio.run(connection.send(command))

    websocket.send_text.assert_awaited_once()
    sent = json.loads(websocket.send_text.call_args[0][0])
    assert sent == CommandEnvelope(command=command).model_dump()
    assert sent["type"] == "command"
    assert sent["command"]["payload"] == {"harness": "codex"}
