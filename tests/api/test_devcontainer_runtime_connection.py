"""Tests for runtime connection state in Devcontainer list/detail responses (VIB-49)."""

from fastapi.testclient import TestClient

WORKER_WS_URL = "/api/v1/runtime/ws"
AGENT_WS_URL = "/api/v1/runtime/agent/ws"

_WORKER_REGISTER = {"type": "runtime_registered", "source": "host_runtime_worker"}


def _agent_register(dc_id: str) -> dict:
    return {
        "type": "runtime_registered",
        "source": "devcontainer_runtime_agent",
        "devcontainer_id": dc_id,
    }


def _create(client: TestClient, name: str = "dc") -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": name, "local_path": f"/tmp/{name}"})
    assert resp.status_code == 201
    return resp.json()["id"]


# --- AC1: list includes worker connection state ---


def test_list_includes_runtime_field(client: TestClient) -> None:
    _create(client)
    body = client.get("/api/v1/devcontainers").json()
    assert "runtime" in body["items"][0]


def test_list_worker_disconnected_by_default(client: TestClient) -> None:
    _create(client)
    body = client.get("/api/v1/devcontainers").json()
    assert body["items"][0]["runtime"]["worker_connected"] is False


def test_list_worker_connected_when_ws_open(client: TestClient) -> None:
    _create(client)
    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        body = client.get("/api/v1/devcontainers").json()
        assert body["items"][0]["runtime"]["worker_connected"] is True


# --- AC2: list/detail include agent connection state ---


def test_list_agent_disconnected_by_default(client: TestClient) -> None:
    _create(client)
    body = client.get("/api/v1/devcontainers").json()
    assert body["items"][0]["runtime"]["agent_connected"] is False


def test_list_agent_connected_when_ws_open(client: TestClient) -> None:
    dc_id = _create(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        body = client.get("/api/v1/devcontainers").json()
        assert body["items"][0]["runtime"]["agent_connected"] is True


def test_detail_includes_runtime_field(client: TestClient) -> None:
    dc_id = _create(client)
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert "runtime" in body


def test_detail_worker_disconnected_by_default(client: TestClient) -> None:
    dc_id = _create(client)
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert body["runtime"]["worker_connected"] is False


def test_detail_worker_connected_when_ws_open(client: TestClient) -> None:
    dc_id = _create(client)
    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
        assert body["runtime"]["worker_connected"] is True


def test_detail_agent_disconnected_by_default(client: TestClient) -> None:
    dc_id = _create(client)
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert body["runtime"]["agent_connected"] is False


def test_detail_agent_connected_when_ws_open(client: TestClient) -> None:
    dc_id = _create(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
        assert body["runtime"]["agent_connected"] is True


# --- AC5/AC6: state changes reflected ---


def test_list_worker_state_changes_after_connect_disconnect(client: TestClient) -> None:
    _create(client)
    # disconnected
    assert (
        client.get("/api/v1/devcontainers").json()["items"][0]["runtime"]["worker_connected"]
        is False
    )
    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        # connected
        assert (
            client.get("/api/v1/devcontainers").json()["items"][0]["runtime"]["worker_connected"]
            is True
        )
    # disconnected again
    assert (
        client.get("/api/v1/devcontainers").json()["items"][0]["runtime"]["worker_connected"]
        is False
    )


def test_detail_worker_state_changes_after_connect_disconnect(client: TestClient) -> None:
    dc_id = _create(client)
    assert (
        client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["worker_connected"] is False
    )
    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        assert (
            client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["worker_connected"]
            is True
        )
    assert (
        client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["worker_connected"] is False
    )


def test_detail_agent_state_changes_after_connect_disconnect(client: TestClient) -> None:
    dc_id = _create(client)
    assert (
        client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["agent_connected"] is False
    )
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        assert (
            client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["agent_connected"]
            is True
        )
    assert (
        client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["agent_connected"] is False
    )


def test_agent_connected_is_per_devcontainer(client: TestClient) -> None:
    dc1 = _create(client, "dc1")
    dc2 = _create(client, "dc2")
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc1))
        assert ws.receive_json() == {"type": "registered"}
        items = {i["id"]: i for i in client.get("/api/v1/devcontainers").json()["items"]}
        assert items[dc1]["runtime"]["agent_connected"] is True
        assert items[dc2]["runtime"]["agent_connected"] is False


def test_worker_connected_is_global_for_all_devcontainers(client: TestClient) -> None:
    dc1 = _create(client, "dc1")
    dc2 = _create(client, "dc2")
    with client.websocket_connect(WORKER_WS_URL) as ws:
        ws.send_json(_WORKER_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        items = {i["id"]: i for i in client.get("/api/v1/devcontainers").json()["items"]}
        assert items[dc1]["runtime"]["worker_connected"] is True
        assert items[dc2]["runtime"]["worker_connected"] is True
