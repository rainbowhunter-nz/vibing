"""Tests for runtime connection state in Devcontainer list/detail responses (VIB-49).

Updated for ADR-0014/0015: single per-devcontainer agent WS; `runtime.state` field.
"""

from fastapi.testclient import TestClient

AGENT_WS_URL = "/api/v1/runtime/agent/ws"


def _agent_register(dc_id: str) -> dict:
    return {
        "type": "runtime_registered",
        "devcontainer_id": dc_id,
    }


def _create(client: TestClient, name: str = "dc") -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": name, "local_path": f"/tmp/{name}"})
    assert resp.status_code == 201
    return resp.json()["id"]


# --- list includes runtime field ---


def test_list_includes_runtime_field(client: TestClient) -> None:
    _create(client)
    body = client.get("/api/v1/devcontainers").json()
    assert "runtime" in body["items"][0]


def test_list_disconnected_by_default(client: TestClient) -> None:
    _create(client)
    body = client.get("/api/v1/devcontainers").json()
    assert body["items"][0]["runtime"]["state"] == "disconnected"


def test_list_connected_when_ws_open(client: TestClient) -> None:
    dc_id = _create(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        body = client.get("/api/v1/devcontainers").json()
        assert body["items"][0]["runtime"]["state"] == "connected"


# --- detail includes runtime field ---


def test_detail_includes_runtime_field(client: TestClient) -> None:
    dc_id = _create(client)
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert "runtime" in body


def test_detail_disconnected_by_default(client: TestClient) -> None:
    dc_id = _create(client)
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert body["runtime"]["state"] == "disconnected"


def test_detail_connected_when_ws_open(client: TestClient) -> None:
    dc_id = _create(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
        assert body["runtime"]["state"] == "connected"


# --- state changes reflected ---


def test_list_state_changes_after_connect_disconnect(client: TestClient) -> None:
    dc_id = _create(client)
    assert (
        client.get("/api/v1/devcontainers").json()["items"][0]["runtime"]["state"] == "disconnected"
    )
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        assert (
            client.get("/api/v1/devcontainers").json()["items"][0]["runtime"]["state"]
            == "connected"
        )
    assert (
        client.get("/api/v1/devcontainers").json()["items"][0]["runtime"]["state"] == "disconnected"
    )


def test_detail_state_changes_after_connect_disconnect(client: TestClient) -> None:
    dc_id = _create(client)
    assert client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["state"] == "disconnected"
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        assert (
            client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["state"] == "connected"
        )
    assert client.get(f"/api/v1/devcontainers/{dc_id}").json()["runtime"]["state"] == "disconnected"


def test_connected_is_per_devcontainer(client: TestClient) -> None:
    dc1 = _create(client, "dc1")
    dc2 = _create(client, "dc2")
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc1))
        assert ws.receive_json() == {"type": "registered"}
        items = {i["id"]: i for i in client.get("/api/v1/devcontainers").json()["items"]}
        assert items[dc1]["runtime"]["state"] == "connected"
        assert items[dc2]["runtime"]["state"] == "disconnected"
