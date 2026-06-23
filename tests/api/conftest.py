from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.main import create_app


class FakeCli:
    def __init__(self) -> None:
        self.running: set[str] = set()
        self.removed: list[str] = []

    async def running_local_folders(self) -> set[str]:
        return self.running

    async def remove(self, local_path: str):
        from vibing_api.core.devcontainer_cli import DevcontainerSuccess

        self.removed.append(local_path)
        return DevcontainerSuccess(operation="remove")


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from vibing_api.core.config import settings

    path = tmp_path / "vibing-test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{path}")
    return path


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    app = create_app()
    app.state.devcontainer_cli = FakeCli()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def devcontainer_id(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work/repo"})
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def fake_cli(client: TestClient) -> FakeCli:
    cli = FakeCli()
    client.app.state.devcontainer_cli = cli
    return cli
