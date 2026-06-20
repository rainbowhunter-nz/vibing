from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from vibing_protocol import Command

from vibing_api.main import create_app


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from vibing_api.core.config import settings

    path = tmp_path / "vibing-test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{path}")
    return path


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def devcontainer_id(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work/repo"})
    assert resp.status_code == 201
    return resp.json()["id"]


class FakeRuntimeConnection:
    """Test double for a connected Devcontainer Runtime; records sent Commands."""

    def __init__(self) -> None:
        self.commands: list[Command] = []

    async def send(self, command: Command) -> None:
        self.commands.append(command)


@pytest.fixture
def connected_runtime(
    client: TestClient, devcontainer_id: str
) -> tuple[str, FakeRuntimeConnection]:
    connection = FakeRuntimeConnection()
    client.app.state.runtime_manager.register(devcontainer_id, connection)  # type: ignore[union-attr]
    return devcontainer_id, connection
