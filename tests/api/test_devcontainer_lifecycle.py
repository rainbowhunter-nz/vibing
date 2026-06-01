import pytest
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.repositories.runtime_events import RuntimeEventRepository

WS_URL = "/api/v1/runtime/ws"
_REGISTER = {"type": "runtime_registered", "source": "host_runtime_worker"}


def _create(client: TestClient, status: str = "created", local_path: str = "/work/repo") -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": local_path})
    assert resp.status_code == 201
    dc_id: str = resp.json()["id"]
    if status != "created":
        patched = client.patch(f"/api/v1/devcontainers/{dc_id}", json={"status": status})
        assert patched.status_code == 200
    return dc_id


def test_start_sends_command_and_returns_202(client: TestClient) -> None:
    dc_id = _create(client, local_path="/work/repo")
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        resp = client.post(f"/api/v1/devcontainers/{dc_id}/start")
        assert resp.status_code == 202
        body = resp.json()
        assert body["id"] == dc_id
        assert body["status"] == "created"  # API does not mutate projected status
        assert ws.receive_json() == {
            "type": "command",
            "command": {
                "type": "start_devcontainer",
                "devcontainer_id": dc_id,
                "agent_session_id": None,
                "payload": {"local_path": "/work/repo"},
            },
        }


def test_stop_sends_command_and_returns_202(client: TestClient) -> None:
    dc_id = _create(client, status="running", local_path="/work/repo")
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        resp = client.post(f"/api/v1/devcontainers/{dc_id}/stop")
        assert resp.status_code == 202
        cmd = ws.receive_json()
        assert cmd["command"]["type"] == "stop_devcontainer"
        assert cmd["command"]["payload"] == {"local_path": "/work/repo"}


def test_start_without_worker_returns_409(client: TestClient) -> None:
    dc_id = _create(client)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/start")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"


def test_stop_without_worker_returns_409(client: TestClient) -> None:
    dc_id = _create(client, status="running")
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/stop")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"


def test_unavailable_worker_writes_no_runtime_event(client: TestClient) -> None:
    dc_id = _create(client)
    client.post(f"/api/v1/devcontainers/{dc_id}/start")
    with get_connection() as conn:
        assert RuntimeEventRepository(conn).list_by_devcontainer(dc_id) == []


@pytest.mark.parametrize("status", ["starting", "running", "stopping"])
def test_start_rejected_from_invalid_states(client: TestClient, status: str) -> None:
    dc_id = _create(client, status=status)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/start")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_DEVCONTAINER_STATE"


@pytest.mark.parametrize("status", ["created", "starting", "stopping", "stopped"])
def test_stop_rejected_from_invalid_states(client: TestClient, status: str) -> None:
    dc_id = _create(client, status=status)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/stop")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_DEVCONTAINER_STATE"


@pytest.mark.parametrize("status", ["created", "stopped", "error"])
def test_start_allowed_states(client: TestClient, status: str) -> None:
    dc_id = _create(client, status=status)
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        resp = client.post(f"/api/v1/devcontainers/{dc_id}/start")
        assert resp.status_code == 202
        assert ws.receive_json()["command"]["type"] == "start_devcontainer"


@pytest.mark.parametrize("status", ["running", "error"])
def test_stop_allowed_states(client: TestClient, status: str) -> None:
    dc_id = _create(client, status=status)
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        resp = client.post(f"/api/v1/devcontainers/{dc_id}/stop")
        assert resp.status_code == 202
        assert ws.receive_json()["command"]["type"] == "stop_devcontainer"


def test_start_unknown_devcontainer_returns_404(client: TestClient) -> None:
    resp = client.post("/api/v1/devcontainers/does-not-exist/start")
    assert resp.status_code == 404
