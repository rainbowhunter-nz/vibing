import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings


def test_get_returns_runtime_and_backend(client: TestClient) -> None:
    body = client.get("/api/v1/settings").json()
    assert body["runtime"] == {
        "docker": None,
        "podman": None,
        "devcontainer_cli": None,
        "claude_code": None,
    }
    assert "backend_host" in body
    assert "backend_port" in body


def test_get_reflects_backend_host_and_port(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "backend_host", "127.0.0.1")
    monkeypatch.setattr(settings, "backend_port", 9000)
    body = client.get("/api/v1/settings").json()
    assert body["backend_host"] == "127.0.0.1"
    assert body["backend_port"] == 9000
