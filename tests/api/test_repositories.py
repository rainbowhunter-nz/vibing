import sqlite3

import pytest

from vibing_api.core.schema import apply_schema
from vibing_api.repositories.devcontainers import DevcontainerRepository


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection)
    connection.commit()
    return connection


def test_devcontainer_round_trip(conn: sqlite3.Connection) -> None:
    repo = DevcontainerRepository(conn)
    created = repo.create("web", "/projects/web")
    fetched = repo.get(created.id)
    assert fetched == created
    assert fetched.status == "created"
    assert repo.list() == [created]


def test_devcontainer_update_only_provided_fields(conn: sqlite3.Connection) -> None:
    from vibing_api.core.vocabularies import DevcontainerStatus

    repo = DevcontainerRepository(conn)
    created = repo.create("web", "/projects/web")
    updated = repo.update(created.id, status=DevcontainerStatus.RUNNING)
    assert updated is not None
    assert updated.status == "running"
    assert updated.name == "web"
    assert updated.updated_at >= created.updated_at


def test_devcontainer_update_no_fields_returns_current(conn: sqlite3.Connection) -> None:
    repo = DevcontainerRepository(conn)
    created = repo.create("web", "/projects/web")
    assert repo.update(created.id) == created


def test_devcontainer_get_and_delete_missing(conn: sqlite3.Connection) -> None:
    repo = DevcontainerRepository(conn)
    assert repo.get("nope") is None
    assert repo.delete("nope") is False
