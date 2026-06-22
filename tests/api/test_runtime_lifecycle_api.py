from fastapi.testclient import TestClient

AGENT_WS_URL = "/api/v1/runtime/agent/ws"


def _create(client: TestClient, name: str = "dc") -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": name, "local_path": f"/tmp/{name}"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_runtime_state_disconnected_by_default(client: TestClient) -> None:
    dc_id = _create(client)
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert body["runtime"]["state"] == "disconnected"


def test_runtime_state_connected_when_ws_open(client: TestClient) -> None:
    dc_id = _create(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json({"type": "runtime_registered", "devcontainer_id": dc_id})
        assert ws.receive_json() == {"type": "registered"}
        body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
        assert body["runtime"]["state"] == "connected"


def test_launching_transient_resolves_to_launching(client: TestClient) -> None:
    from vibing_api.core.vocabularies import RuntimeState

    dc_id = _create(client)
    client.app.state.live_state.set_runtime_transient(dc_id, RuntimeState.LAUNCHING)  # type: ignore[union-attr]
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert body["runtime"]["state"] == "launching"


def test_register_clears_launching_transient(client: TestClient) -> None:
    from vibing_api.core.vocabularies import RuntimeState

    dc_id = _create(client)
    client.app.state.live_state.set_runtime_transient(dc_id, RuntimeState.LAUNCHING)  # type: ignore[union-attr]
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json({"type": "runtime_registered", "devcontainer_id": dc_id})
        assert ws.receive_json() == {"type": "registered"}
        assert client.app.state.live_state.get_runtime_transient(dc_id) is None  # type: ignore[union-attr]


def test_stop_runtime_endpoint_returns_202(client: TestClient) -> None:
    dc_id = _create(client)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/stop-runtime")
    assert resp.status_code == 202


def test_runtime_logs_endpoint_returns_content(client: TestClient) -> None:
    dc_id = _create(client)

    async def fake_read_log(local_path: str) -> str | None:
        return "hello from the runtime"

    client.app.state.runtime_service.read_log = fake_read_log  # type: ignore[union-attr]
    body = client.get(f"/api/v1/devcontainers/{dc_id}/runtime-logs").json()
    assert body == {"content": "hello from the runtime"}


def test_stop_runtime_not_found(client: TestClient) -> None:
    resp = client.post("/api/v1/devcontainers/nope/stop-runtime")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"
