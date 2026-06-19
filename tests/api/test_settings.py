import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.core.database import get_connection
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository


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


def test_list_harness_credentials_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/settings/harness-credentials")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_harness_credentials_returns_configured_flag_only(client: TestClient) -> None:
    with get_connection() as conn:
        HarnessCredentialRepository(conn).upsert("codex", {"secret": "s3cr3t"})
        conn.commit()

    resp = client.get("/api/v1/settings/harness-credentials")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{"name": "codex", "configured": True}]
    # Confirm blob is absent from response
    assert "blob" not in body[0]
    assert "secret" not in str(body)


def test_put_harness_credential_upserts_and_returns_view(client: TestClient) -> None:
    resp = client.put(
        "/api/v1/settings/harness-credentials/codex",
        json={"blob": {"api_key": "sk-abc"}},
    )
    assert resp.status_code == 200
    assert resp.json() == {"name": "codex", "configured": True}

    # Verify stored in DB
    with get_connection() as conn:
        stored = HarnessCredentialRepository(conn).get("codex")
    assert stored == {"api_key": "sk-abc"}


def test_put_harness_credential_overwrites_existing(client: TestClient) -> None:
    client.put("/api/v1/settings/harness-credentials/codex", json={"blob": {"v": 1}})
    client.put("/api/v1/settings/harness-credentials/codex", json={"blob": {"v": 2}})
    with get_connection() as conn:
        stored = HarnessCredentialRepository(conn).get("codex")
    assert stored == {"v": 2}


def test_list_harness_credentials_never_returns_secret_blob(client: TestClient) -> None:
    with get_connection() as conn:
        HarnessCredentialRepository(conn).upsert("cursor", {"password": "super-secret"})
        conn.commit()

    resp = client.get("/api/v1/settings/harness-credentials")
    raw = resp.text
    assert "super-secret" not in raw
    assert "password" not in raw
