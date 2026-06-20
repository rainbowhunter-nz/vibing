"""Tests for POST /devcontainers/{id}/harnesses/{name}/install."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


def _create_dc(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work/repo"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_install_sends_install_command(client: TestClient) -> None:
    dc_id = _create_dc(client)
    ws_mock = AsyncMock()
    ws_mock.send_json = AsyncMock()
    client.app.state.runtime_manager._connections[dc_id] = ws_mock  # type: ignore[union-attr]

    resp = client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/install")
    assert resp.status_code == 202

    sent = ws_mock.send_json.call_args.args[0]
    assert sent["command"]["type"] == "install_harness"
    assert sent["command"]["payload"] == {"harness": "codex"}


def test_install_409_when_no_runtime(client: TestClient) -> None:
    dc_id = _create_dc(client)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/install")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"
