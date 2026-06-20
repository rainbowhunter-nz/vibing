"""Tests for the harnesses API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from vibing_protocol import CommandType

from vibing_api.core.database import get_connection
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository
from vibing_api.repositories.harness_status import HarnessStatusRepository

if TYPE_CHECKING:
    from tests.api.conftest import FakeRuntimeConnection


def _seed_harnesses(dc_id: str) -> None:
    with get_connection() as conn:
        repo = HarnessStatusRepository(conn)
        repo.upsert(dc_id, "codex", installed=True, authenticated=False)
        repo.upsert(dc_id, "gh", installed=True, authenticated=True)
        conn.commit()


def test_list_harnesses_returns_seeded_rows(client: TestClient, devcontainer_id: str) -> None:
    _seed_harnesses(devcontainer_id)
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.status_code == 200
    items = {i["name"]: i for i in resp.json()["items"]}
    assert set(items) == {"codex", "gh"}
    assert items["codex"]["installed"] is True
    assert items["codex"]["authenticated"] is False
    assert items["gh"]["authenticated"] is True


def test_list_harnesses_empty_when_no_rows(client: TestClient, devcontainer_id: str) -> None:
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_list_harnesses_404_for_unknown_devcontainer(client: TestClient) -> None:
    resp = client.get("/api/v1/devcontainers/does-not-exist/harnesses")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"


def test_authenticate_harness_returns_202_when_connected(
    client: TestClient, connected_runtime: tuple[str, FakeRuntimeConnection]
) -> None:
    dc_id, _ = connected_runtime
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")
    assert resp.status_code == 202


def test_authenticate_harness_sends_command_with_correct_harness(
    client: TestClient, connected_runtime: tuple[str, FakeRuntimeConnection]
) -> None:
    dc_id, connection = connected_runtime
    client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")

    assert len(connection.commands) == 1
    command = connection.commands[0]
    assert command.type == CommandType.AUTHENTICATE_HARNESS
    assert command.devcontainer_id == dc_id
    assert command.payload == {"harness": "codex", "credentials": {}}


def test_authenticate_harness_409_when_not_connected(
    client: TestClient, devcontainer_id: str
) -> None:
    resp = client.post(f"/api/v1/devcontainers/{devcontainer_id}/harnesses/codex/authenticate")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"


def test_authenticate_harness_carries_stored_credentials(
    client: TestClient, connected_runtime: tuple[str, FakeRuntimeConnection]
) -> None:
    dc_id, connection = connected_runtime
    with get_connection() as conn:
        HarnessCredentialRepository(conn).upsert("codex", {"api_key": "sk-secret"})
        conn.commit()

    client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")

    assert connection.commands[0].payload == {
        "harness": "codex",
        "credentials": {"api_key": "sk-secret"},
    }


def test_authenticate_harness_empty_credentials_when_none_stored(
    client: TestClient, connected_runtime: tuple[str, FakeRuntimeConnection]
) -> None:
    dc_id, connection = connected_runtime
    client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/authenticate")
    assert connection.commands[0].payload == {"harness": "codex", "credentials": {}}
