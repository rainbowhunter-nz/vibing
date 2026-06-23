"""Tests for POST /devcontainers/{id}/harnesses/{name}/install and .../authenticate."""

from __future__ import annotations

import vibing_api.core.harness_service as harness_service
from vibing_harness import HarnessStatus


async def _fake_install_stream(ex, name):
    yield "installing"
    yield "done"


async def _fake_authenticate_stream(ex, name, blob):
    yield "authenticating"
    yield "ok"


async def _fake_refresh(live, devcontainer_id, ex, broadcaster=None):
    return [HarnessStatus("codex", True, True)]


def test_install_streams_text(client, devcontainer_id, monkeypatch) -> None:
    monkeypatch.setattr(harness_service, "install_stream", _fake_install_stream)
    monkeypatch.setattr(harness_service, "refresh", _fake_refresh)

    resp = client.post(f"/api/v1/devcontainers/{devcontainer_id}/harnesses/codex/install")
    assert resp.status_code == 200
    assert "installing" in resp.text
    assert "done" in resp.text


def test_authenticate_streams_text(client, devcontainer_id, monkeypatch) -> None:
    monkeypatch.setattr(harness_service, "authenticate_stream", _fake_authenticate_stream)
    monkeypatch.setattr(harness_service, "refresh", _fake_refresh)

    resp = client.post(f"/api/v1/devcontainers/{devcontainer_id}/harnesses/codex/authenticate")
    assert resp.status_code == 200
    assert "authenticating" in resp.text
    assert "ok" in resp.text


def test_install_404_for_unknown_devcontainer(client) -> None:
    resp = client.post("/api/v1/devcontainers/dc-missing/harnesses/codex/install")
    assert resp.status_code == 404


def test_authenticate_404_for_unknown_devcontainer(client) -> None:
    resp = client.post("/api/v1/devcontainers/dc-missing/harnesses/codex/authenticate")
    assert resp.status_code == 404
