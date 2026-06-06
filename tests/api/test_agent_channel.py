"""Tests for the agent WebSocket channel and AgentRegistry."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.core.runtime_channel import AgentRegistry
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


# --- AgentRegistry unit tests (AC7) ---


@pytest.fixture
def manager() -> AgentRegistry:
    return AgentRegistry()


def _ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


def test_register_succeeds(manager: AgentRegistry) -> None:
    ws = _ws()
    assert manager.register("dc-1", ws) is True
    assert manager.is_connected("dc-1")


def test_reject_missing_id(manager: AgentRegistry) -> None:
    # Simulate the route rejecting it: is_connected("") should be False by default
    assert not manager.is_connected("")
    assert not manager.is_connected("dc-nonexistent")


def test_reject_duplicate(manager: AgentRegistry) -> None:
    ws1, ws2 = _ws(), _ws()
    assert manager.register("dc-1", ws1) is True
    assert manager.register("dc-1", ws2) is False


def test_route_to_match(manager: AgentRegistry) -> None:
    ws1, ws2 = _ws(), _ws()
    manager.register("dc-1", ws1)
    manager.register("dc-2", ws2)
    from vibing_protocol import Command
    import asyncio

    cmd = Command(type="start_agent_session", devcontainer_id="dc-1")
    asyncio.run(manager.send_command(cmd))
    ws1.send_json.assert_called_once()
    ws2.send_json.assert_not_called()


def test_unavailable_when_none(manager: AgentRegistry) -> None:
    from vibing_protocol import Command
    import asyncio

    cmd = Command(type="start_agent_session", devcontainer_id="dc-missing")
    with pytest.raises(RuntimeError, match="No runtime connection registered"):
        asyncio.run(manager.send_command(cmd))


def test_unregister(manager: AgentRegistry) -> None:
    ws = _ws()
    manager.register("dc-1", ws)
    manager.unregister("dc-1", ws)
    assert not manager.is_connected("dc-1")


# --- transcript request/reply (VIB-104, ADR-0009) ---


def test_request_transcript_sends_request_and_resolves(manager: AgentRegistry) -> None:
    import asyncio

    ws = _ws()
    manager.register("dc-1", ws)

    async def scenario() -> list:
        task = asyncio.create_task(manager.request_transcript("dc-1", "sess-1", timeout=5.0))
        await asyncio.sleep(0)  # let the send happen and the future register
        sent = ws.send_json.call_args.args[0]
        assert sent["type"] == "transcript_request"
        assert sent["agent_session_id"] == "sess-1"
        request_id = sent["request_id"]
        assert request_id  # a fresh cp-side id
        manager.resolve_transcript(request_id, [{"role": "user", "blocks": [], "at": "t"}])
        return await task

    turns = asyncio.run(scenario())
    assert turns == [{"role": "user", "blocks": [], "at": "t"}]


def test_request_transcript_times_out(manager: AgentRegistry) -> None:
    import asyncio

    ws = _ws()
    manager.register("dc-1", ws)

    async def scenario() -> None:
        with pytest.raises(asyncio.TimeoutError):
            await manager.request_transcript("dc-1", "sess-1", timeout=0.01)

    asyncio.run(scenario())


def test_disconnect_fails_inflight_futures(manager: AgentRegistry) -> None:
    import asyncio

    ws = _ws()
    manager.register("dc-1", ws)

    async def scenario() -> None:
        task = asyncio.create_task(manager.request_transcript("dc-1", "sess-1", timeout=5.0))
        await asyncio.sleep(0)
        manager.unregister("dc-1", ws)  # connection drops
        with pytest.raises(ConnectionError):
            await task

    asyncio.run(scenario())


def test_resolve_unknown_request_is_noop(manager: AgentRegistry) -> None:
    manager.resolve_transcript("never-registered", [])  # must not raise


def test_request_transcript_no_agent_raises(manager: AgentRegistry) -> None:
    import asyncio

    async def scenario() -> None:
        with pytest.raises(RuntimeError):
            await manager.request_transcript("dc-missing", "sess-1", timeout=5.0)

    asyncio.run(scenario())
