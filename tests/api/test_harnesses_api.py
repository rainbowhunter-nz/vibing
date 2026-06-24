"""Tests for GET /devcontainers/{id}/harnesses and POST .../refresh."""

from __future__ import annotations

import vibing_api.core.harness_service as harness_service
from vibing_harness import HarnessStatus


def test_get_harnesses_unknown_when_no_cache(client, devcontainer_id) -> None:
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "known": False}


def test_get_harnesses_unknown_unknown_id(client) -> None:
    resp = client.get("/api/v1/devcontainers/dc-x/harnesses")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "known": False}


def test_get_harnesses_computes_on_demand_when_running_and_uncached(
    client, devcontainer_id, monkeypatch
) -> None:
    # Container already running before vibing cached its status (e.g. it was up before
    # vibing started, or vibing restarted). GET must self-heal by computing, not stay
    # known=False forever (the frontend would spin indefinitely).
    async def fake_compute(ex):
        return [HarnessStatus("codex", True, False)]

    monkeypatch.setattr(harness_service, "compute_status", fake_compute)
    client.app.state.devcontainer_cli.running.add("/work/repo")

    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.status_code == 200
    body = resp.json()
    assert body["known"] is True
    assert [i["name"] for i in body["items"]] == ["codex"]


def test_get_harnesses_stays_unknown_when_not_running(client, devcontainer_id, monkeypatch) -> None:
    # Not running: no compute (devcontainer exec would fail) -- stays unknown.
    async def fake_compute(ex):
        raise AssertionError("must not compute when the container is not running")

    monkeypatch.setattr(harness_service, "compute_status", fake_compute)
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "known": False}


def test_refresh_recomputes_and_caches(client, devcontainer_id, monkeypatch) -> None:
    async def fake_compute(ex):
        return [HarnessStatus("codex", True, True), HarnessStatus("cursor", False, False)]

    monkeypatch.setattr(harness_service, "compute_status", fake_compute)

    resp = client.post(f"/api/v1/devcontainers/{devcontainer_id}/harnesses/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["known"] is True
    assert {i["name"]: i["installed"] for i in body["items"]} == {"codex": True, "cursor": False}


def test_refresh_404_for_unknown_devcontainer(client) -> None:
    resp = client.post("/api/v1/devcontainers/dc-missing/harnesses/refresh")
    assert resp.status_code == 404
