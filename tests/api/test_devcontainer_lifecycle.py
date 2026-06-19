"""Devcontainer lifecycle tests — wired to the in-process DevcontainerService (ADR-0014).

All tests use the full-app `client` fixture (needs Task 2.5 wiring) — expected-red until then.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.devcontainer_service import DevcontainerService


def _create(client: TestClient, status: str = "created", local_path: str = "/work/repo") -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": local_path})
    assert resp.status_code == 201
    dc_id: str = resp.json()["id"]
    if status != "created":
        patched = client.patch(f"/api/v1/devcontainers/{dc_id}", json={"status": status})
        assert patched.status_code == 200
    return dc_id


def _fake_service() -> DevcontainerService:
    """DevcontainerService with a no-op adapter and injector."""
    adapter = MagicMock()
    adapter.start = AsyncMock(return_value=MagicMock(payload={}))
    adapter.stop = AsyncMock(return_value=MagicMock())
    injector = MagicMock()
    injector.inject = AsyncMock()
    return DevcontainerService(adapter, injector)


def test_start_returns_202(client: TestClient) -> None:
    dc_id = _create(client, local_path="/work/repo")
    client.app.state.devcontainer_service = _fake_service()  # type: ignore[union-attr]
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/start")
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"] == dc_id
    assert body["status"] == "created"  # API returns snapshot; background task mutates later


def test_stop_returns_202(client: TestClient) -> None:
    dc_id = _create(client, status="running", local_path="/work/repo")
    client.app.state.devcontainer_service = _fake_service()  # type: ignore[union-attr]
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/stop")
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"] == dc_id
    assert body["status"] == "running"


def test_start_invokes_service(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import vibing_api.api.routes.devcontainers as dc_routes

    dc_id = _create(client, local_path="/work/repo")
    svc = MagicMock()
    svc.start = AsyncMock()
    client.app.state.devcontainer_service = svc  # type: ignore[union-attr]

    captured: list[object] = []

    def _capture(coro) -> None:  # type: ignore[no-untyped-def]
        captured.append(coro)
        coro.close()  # prevent "coroutine never awaited" warning

    monkeypatch.setattr(dc_routes, "run_in_background", _capture)

    resp = client.post(f"/api/v1/devcontainers/{dc_id}/start")
    assert resp.status_code == 202
    assert resp.json()["id"] == dc_id
    assert len(captured) == 1
    # Behaviorally assert service.start was called with correct args
    svc.start.assert_called_once_with(dc_id, "/work/repo")


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
    client.app.state.devcontainer_service = _fake_service()  # type: ignore[union-attr]
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/start")
    assert resp.status_code == 202


@pytest.mark.parametrize("status", ["running", "error"])
def test_stop_allowed_states(client: TestClient, status: str) -> None:
    dc_id = _create(client, status=status)
    client.app.state.devcontainer_service = _fake_service()  # type: ignore[union-attr]
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/stop")
    assert resp.status_code == 202


def test_start_unknown_devcontainer_returns_404(client: TestClient) -> None:
    resp = client.post("/api/v1/devcontainers/does-not-exist/start")
    assert resp.status_code == 404
