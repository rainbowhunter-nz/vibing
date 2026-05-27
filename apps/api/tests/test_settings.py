import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.main import create_app


def test_get_returns_defaults_when_no_file(client: TestClient, settings_file: Path) -> None:
    assert not settings_file.exists()
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_storage_location"] == str(settings_file.parent / "workspaces")
    assert body["editor_preference"] is None
    assert body["notifications_enabled"] is None
    assert body["runtime"] == {
        "docker": None,
        "podman": None,
        "devcontainer_cli": None,
        "claude_code": None,
    }


def test_get_reflects_backend_host_and_port(
    client: TestClient, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "backend_host", "127.0.0.1")
    monkeypatch.setattr(settings, "backend_port", 9000)
    body = client.get("/api/v1/settings").json()
    assert body["backend_host"] == "127.0.0.1"
    assert body["backend_port"] == 9000


def test_patch_persists_and_roundtrips(client: TestClient, settings_file: Path) -> None:
    response = client.patch(
        "/api/v1/settings", json={"workspace_storage_location": "/tmp/ws"}
    )
    assert response.status_code == 200
    assert response.json()["workspace_storage_location"] == "/tmp/ws"
    assert json.loads(settings_file.read_text())["workspace_storage_location"] == "/tmp/ws"
    assert client.get("/api/v1/settings").json()["workspace_storage_location"] == "/tmp/ws"


def test_patch_survives_restart(client: TestClient, settings_file: Path) -> None:
    client.patch("/api/v1/settings", json={"workspace_storage_location": "/tmp/persist"})
    with TestClient(create_app()) as fresh:
        body = fresh.get("/api/v1/settings").json()
    assert body["workspace_storage_location"] == "/tmp/persist"


def test_patch_rejects_empty_value(client: TestClient, settings_file: Path) -> None:
    response = client.patch(
        "/api/v1/settings", json={"workspace_storage_location": "   "}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_strips_surrounding_whitespace(client: TestClient, settings_file: Path) -> None:
    response = client.patch(
        "/api/v1/settings", json={"workspace_storage_location": "  /tmp/ws  "}
    )
    assert response.status_code == 200
    assert response.json()["workspace_storage_location"] == "/tmp/ws"
    assert json.loads(settings_file.read_text())["workspace_storage_location"] == "/tmp/ws"


def test_patch_rejects_unknown_field(client: TestClient, settings_file: Path) -> None:
    response = client.patch(
        "/api/v1/settings",
        json={"workspace_storage_location": "/tmp/ws", "backend_host": "0.0.0.0"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
