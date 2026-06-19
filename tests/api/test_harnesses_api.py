"""Tests for the harnesses API endpoints."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from vibing_protocol import CommandType

from vibing_api.core.database import get_connection
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository
from vibing_api.repositories.harness_status import HarnessStatusRepository


def _create_dc(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work/repo"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _seed_harnesses(dc_id: str) -> None:
    with get_connection() as conn:
        repo = HarnessStatusRepository(conn)
        repo.upsert(dc_id, "codex", installed=True, authenticated=False)
        repo.upsert(dc_id, "gh", installed=True, authenticated=True)
        conn.commit()


def test_list_harnesses_returns_seeded_rows(client: TestClient) -> None:
    dc_id = _create_dc(client)
    _seed_harnesses(dc_id)
    resp = client.get(f"/api/v1/devcontainers/{dc_id}/harnesses")
    assert resp.status_code == 200
    items = {i["name"]: i for i in resp.json()["items"]}
    assert set(items) == {"codex", "gh"}
    assert items["codex"]["installed"] is True
    assert items["codex"]["authenticated"] is False
    assert items["gh"]["authenticated"] is True


def test_list_harnesses_empty_when_no_rows(client: TestClient) -> None:
    dc_id = _create_dc(client)
    resp = client.get(f"/api/v1/devcontainers/{dc_id}/harnesses")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_list_harnesses_404_for_unknown_devcontainer(client: TestClient) -> None:
    resp = client.get("/api/v1/devcontainers/does-not-exist/harnesses")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"


def test_authenticate_harness_returns_202_when_connected(client: TestClient) -> None:
    dc_id = _create_dc(client)
    ws_mock = AsyncMock()
    ws_mock.send_json = AsyncMock()
    client.app.state.runtime_manager._connections[dc_id] = ws_mock  # type: ignore[union-attr]

    resp = client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")
    assert resp.status_code == 202


def test_authenticate_harness_sends_command_with_correct_harness(client: TestClient) -> None:
    dc_id = _create_dc(client)
    ws_mock = AsyncMock()
    ws_mock.send_json = AsyncMock()
    client.app.state.runtime_manager._connections[dc_id] = ws_mock  # type: ignore[union-attr]

    client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")

    ws_mock.send_json.assert_awaited_once()
    envelope = ws_mock.send_json.call_args[0][0]
    assert envelope["command"]["type"] == CommandType.AUTHENTICATE_HARNESS
    assert envelope["command"]["payload"]["harness"] == "codex"
    assert envelope["command"]["devcontainer_id"] == dc_id
    assert "credentials" in envelope["command"]["payload"]


def test_authenticate_harness_409_when_not_connected(client: TestClient) -> None:
    dc_id = _create_dc(client)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"


def test_authenticate_harness_carries_stored_credentials(client: TestClient) -> None:
    dc_id = _create_dc(client)
    with get_connection() as conn:
        HarnessCredentialRepository(conn).upsert("codex", {"api_key": "sk-secret"})
        conn.commit()

    ws_mock = AsyncMock()
    ws_mock.send_json = AsyncMock()
    client.app.state.runtime_manager._connections[dc_id] = ws_mock  # type: ignore[union-attr]

    client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")

    envelope = ws_mock.send_json.call_args[0][0]
    assert envelope["command"]["payload"]["credentials"] == {"api_key": "sk-secret"}


def test_authenticate_harness_empty_credentials_when_none_stored(client: TestClient) -> None:
    dc_id = _create_dc(client)
    ws_mock = AsyncMock()
    ws_mock.send_json = AsyncMock()
    client.app.state.runtime_manager._connections[dc_id] = ws_mock  # type: ignore[union-attr]

    client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")

    envelope = ws_mock.send_json.call_args[0][0]
    assert envelope["command"]["payload"]["credentials"] == {}
