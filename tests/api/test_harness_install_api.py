"""Tests for POST /devcontainers/{id}/harnesses/{name}/install."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from vibing_protocol import CommandType

if TYPE_CHECKING:
    from tests.api.conftest import FakeRuntimeConnection


def test_install_sends_install_command(
    client: TestClient, connected_runtime: tuple[str, FakeRuntimeConnection]
) -> None:
    dc_id, connection = connected_runtime
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/install")
    assert resp.status_code == 202

    assert len(connection.commands) == 1
    command = connection.commands[0]
    assert command.type == CommandType.INSTALL_HARNESS
    assert command.payload == {"harness": "codex"}


def test_install_409_when_no_runtime(client: TestClient, devcontainer_id: str) -> None:
    resp = client.post(f"/api/v1/devcontainers/{devcontainer_id}/harnesses/codex/install")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"
