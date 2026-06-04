"""Tests for GET /api/v1/runtime/status (VIB-71)."""

from fastapi.testclient import TestClient

WORKER_WS_URL = "/api/v1/runtime/ws"
_WORKER_REGISTER = {"type": "runtime_registered", "source": "host_runtime_worker"}


def test_runtime_status_returns_200(client: TestClient) -> None:
    resp = client.get("/api/v1/runtime/status")
    assert resp.status_code == 200


def test_runtime_status_worker_disconnected_by_default(client: TestClient) -> None:
    body = client.get("/api/v1/runtime/status").json()
    assert body["worker_connected"] is False


def test_runtime_status_worker_connected_when_ws_open(client: TestClient) -> None:
    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        body = client.get("/api/v1/runtime/status").json()
        assert body["worker_connected"] is True


def test_runtime_status_worker_disconnected_after_ws_closes(client: TestClient) -> None:
    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        ws.receive_json()
    body = client.get("/api/v1/runtime/status").json()
    assert body["worker_connected"] is False


def test_runtime_status_invalidation_on_worker_connect(client: TestClient) -> None:
    """Worker connect broadcasts `runtime` scope — existing test_runtime_connection_invalidations
    covers the broadcast; here we just confirm the status endpoint reflects the live state."""
    from vibing_api.core.broadcaster import SseEvent

    class CapturingBroadcaster:
        def __init__(self) -> None:
            self.published: list[SseEvent] = []

        def publish(self, event: SseEvent) -> None:
            self.published.append(event)

    spy = CapturingBroadcaster()
    client.app.state.broadcaster = spy  # type: ignore[attr-defined]

    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        ws.receive_json()
        # Status reflects connected state
        assert client.get("/api/v1/runtime/status").json()["worker_connected"] is True
        # And broadcast was emitted
        assert any(e.scope == "runtime" for e in spy.published)
