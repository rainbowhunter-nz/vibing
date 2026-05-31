"""Tests for the agent WebSocket channel and AgentConnectionManager."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.core.runtime_channel import AgentConnectionManager
from vibing_api.repositories.runtime_events import RuntimeEventRepository

AGENT_WS_URL = "/api/v1/runtime/agent/ws"

_REGISTER = {
    "type": "runtime_registered",
    "source": "devcontainer_runtime_agent",
    "devcontainer_id": "dc-1",
}


def _event_envelope(dc_id: str, event_type: str = "agent_session_started") -> dict[str, Any]:
    return {
        "type": "runtime_event",
        "event": {
            "event_type": event_type,
            "source": "devcontainer_runtime_agent",
            "devcontainer_id": dc_id,
        },
    }


# --- route tests ---


def test_agent_registers(client: TestClient) -> None:
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_REGISTER)
        assert ws.receive_json() == {"type": "registered"}


def test_agent_missing_id_is_rejected(client: TestClient) -> None:
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json({"type": "runtime_registered", "source": "devcontainer_runtime_agent"})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4400


def test_agent_wrong_source_is_rejected(client: TestClient) -> None:
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(
            {
                "type": "runtime_registered",
                "source": "host_runtime_worker",
                "devcontainer_id": "dc-1",
            }
        )
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4400


def test_duplicate_agent_is_rejected(client: TestClient) -> None:
    with client.websocket_connect(AGENT_WS_URL) as ws1:
        ws1.send_json(_REGISTER)
        assert ws1.receive_json() == {"type": "registered"}
        with client.websocket_connect(AGENT_WS_URL) as ws2:
            ws2.send_json(_REGISTER)
            with pytest.raises(WebSocketDisconnect) as exc:
                ws2.receive_json()
            assert exc.value.code == 4409


def test_agent_slot_freed_after_disconnect(client: TestClient) -> None:
    with client.websocket_connect(AGENT_WS_URL) as ws1:
        ws1.send_json(_REGISTER)
        assert ws1.receive_json() == {"type": "registered"}
    with client.websocket_connect(AGENT_WS_URL) as ws2:
        ws2.send_json(_REGISTER)
        assert ws2.receive_json() == {"type": "registered"}


def test_agent_event_persisted(client: TestClient) -> None:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"})
    assert resp.status_code == 201
    dc_id = resp.json()["id"]
    register = {**_REGISTER, "devcontainer_id": dc_id}
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(register)
        assert ws.receive_json() == {"type": "registered"}
        ws.send_json(_event_envelope(dc_id))
    with get_connection() as conn:
        events = RuntimeEventRepository(conn).list_by_devcontainer(dc_id)
        assert len(events) == 1
        assert events[0].source == "devcontainer_runtime_agent"


# --- AgentConnectionManager unit tests (AC7) ---


@pytest.fixture
def manager() -> AgentConnectionManager:
    return AgentConnectionManager()


def _ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


def test_register_succeeds(manager: AgentConnectionManager) -> None:
    ws = _ws()
    assert manager.register_agent("dc-1", ws) is True
    assert manager.is_agent_connected("dc-1")


def test_reject_missing_id(manager: AgentConnectionManager) -> None:
    # Simulate the route rejecting it: is_agent_connected("") should be False by default
    assert not manager.is_agent_connected("")
    assert not manager.is_agent_connected("dc-nonexistent")


def test_reject_duplicate(manager: AgentConnectionManager) -> None:
    ws1, ws2 = _ws(), _ws()
    assert manager.register_agent("dc-1", ws1) is True
    assert manager.register_agent("dc-1", ws2) is False


def test_route_to_match(manager: AgentConnectionManager) -> None:
    ws1, ws2 = _ws(), _ws()
    manager.register_agent("dc-1", ws1)
    manager.register_agent("dc-2", ws2)
    from vibing_protocol import Command
    import asyncio

    cmd = Command(type="start_agent_session", devcontainer_id="dc-1")
    asyncio.run(manager.send_command(cmd))
    ws1.send_json.assert_called_once()
    ws2.send_json.assert_not_called()


def test_unavailable_when_none(manager: AgentConnectionManager) -> None:
    from vibing_protocol import Command
    import asyncio

    cmd = Command(type="start_agent_session", devcontainer_id="dc-missing")
    with pytest.raises(RuntimeError, match="No Devcontainer Runtime Agent"):
        asyncio.run(manager.send_command(cmd))


def test_unregister(manager: AgentConnectionManager) -> None:
    ws = _ws()
    manager.register_agent("dc-1", ws)
    manager.unregister_agent("dc-1", ws)
    assert not manager.is_agent_connected("dc-1")
