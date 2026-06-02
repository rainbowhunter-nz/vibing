"""Tests for VIB-46: SSE invalidation broadcasts on runtime connection/disconnection."""

from fastapi.testclient import TestClient

from vibing_api.core.broadcaster import SseEvent

WORKER_WS_URL = "/api/v1/runtime/ws"
AGENT_WS_URL = "/api/v1/runtime/agent/ws"

_WORKER_REGISTER = {"type": "runtime_registered", "source": "host_runtime_worker"}
_DC_ID = "dc-42"
_AGENT_REGISTER = {
    "type": "runtime_registered",
    "source": "devcontainer_runtime_agent",
    "devcontainer_id": _DC_ID,
}


class CapturingBroadcaster:
    def __init__(self) -> None:
        self.published: list[SseEvent] = []

    def publish(self, event: SseEvent) -> None:
        self.published.append(event)


# ---------------------------------------------------------------------------
# AC1: Host Runtime Worker connect + disconnect broadcasts
# ---------------------------------------------------------------------------


def test_worker_connect_broadcasts_runtime_invalidation(client: TestClient) -> None:
    spy = CapturingBroadcaster()
    client.app.state.broadcaster = spy  # type: ignore[attr-defined]

    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        assert len(spy.published) == 1
        assert spy.published[0].scope == "runtime"

    # context exit triggers disconnect
    assert len(spy.published) == 2
    assert spy.published[1].scope == "runtime"


def test_worker_disconnect_broadcasts_runtime_invalidation(client: TestClient) -> None:
    spy = CapturingBroadcaster()
    client.app.state.broadcaster = spy  # type: ignore[attr-defined]

    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        ws.receive_json()
        before_disconnect = len(spy.published)

    assert len(spy.published) == before_disconnect + 1
    assert spy.published[-1].scope == "runtime"


# ---------------------------------------------------------------------------
# AC2 / AC6: Devcontainer Runtime Agent connect + disconnect broadcasts with devcontainer_id
# ---------------------------------------------------------------------------


def test_agent_connect_broadcasts_runtime_invalidation_with_dc_id(client: TestClient) -> None:
    spy = CapturingBroadcaster()
    client.app.state.broadcaster = spy  # type: ignore[attr-defined]

    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_AGENT_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        assert len(spy.published) == 1
        evt = spy.published[0]
        assert evt.scope == "runtime"
        assert evt.ids == [_DC_ID]

    assert len(spy.published) == 2
    assert spy.published[1].scope == "runtime"
    assert spy.published[1].ids == [_DC_ID]


def test_agent_disconnect_broadcasts_runtime_invalidation_with_dc_id(client: TestClient) -> None:
    spy = CapturingBroadcaster()
    client.app.state.broadcaster = spy  # type: ignore[attr-defined]

    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_AGENT_REGISTER)
        ws.receive_json()
        before_disconnect = len(spy.published)

    assert len(spy.published) == before_disconnect + 1
    evt = spy.published[-1]
    assert evt.scope == "runtime"
    assert evt.ids == [_DC_ID]


# ---------------------------------------------------------------------------
# Correctness: rejected / invalid connections must NOT broadcast
# ---------------------------------------------------------------------------


def test_rejected_worker_does_not_broadcast(client: TestClient) -> None:
    """Second worker rejected (slot taken) must not emit a connect invalidation."""
    spy = CapturingBroadcaster()
    client.app.state.broadcaster = spy  # type: ignore[attr-defined]

    from fastapi import WebSocketDisconnect
    import pytest

    with client.websocket_connect(WORKER_WS_URL) as ws1:
        ws1.send_json(_WORKER_REGISTER)
        ws1.receive_json()
        connect_count = len(spy.published)  # 1 from first connect

        with client.websocket_connect(WORKER_WS_URL) as ws2:
            ws2.send_json(_WORKER_REGISTER)
            with pytest.raises(WebSocketDisconnect):
                ws2.receive_json()
        # rejected ws2 must not have added any events
        assert len(spy.published) == connect_count


def test_invalid_envelope_does_not_broadcast(client: TestClient) -> None:
    """Invalid envelope (returns None from register) must not emit any broadcast."""
    spy = CapturingBroadcaster()
    client.app.state.broadcaster = spy  # type: ignore[attr-defined]

    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json({"type": "runtime_registered", "source": "garbage"})
        # no registered response — but still connected

    assert spy.published == []


def test_rejected_agent_does_not_broadcast(client: TestClient) -> None:
    """Agent rejected (duplicate slot) must not emit an extra connect invalidation."""
    spy = CapturingBroadcaster()
    client.app.state.broadcaster = spy  # type: ignore[attr-defined]

    from fastapi import WebSocketDisconnect
    import pytest

    with client.websocket_connect(AGENT_WS_URL) as ws1:
        ws1.send_json(_AGENT_REGISTER)
        ws1.receive_json()
        connect_count = len(spy.published)  # 1 from first connect

        with client.websocket_connect(AGENT_WS_URL) as ws2:
            ws2.send_json(_AGENT_REGISTER)
            with pytest.raises(WebSocketDisconnect):
                ws2.receive_json()
        assert len(spy.published) == connect_count
