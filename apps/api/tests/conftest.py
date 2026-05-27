from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.main import create_app


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "vibing-test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{path}")
    return path


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client
