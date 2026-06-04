"""Tests for inbox-event read/resolved actions (VIB-75)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.core.schema import apply_schema
from vibing_api.core.vocabularies import InboxEventStatus
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.inbox import InboxRepository

# `client` and `db_path` fixtures come from tests/api/conftest.py.


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection)
    connection.commit()
    return connection


def _make_devcontainer(conn: sqlite3.Connection) -> str:
    return DevcontainerRepository(conn).create("dc", "/tmp/dc").id


class TestMarkRead:
    def test_marks_unread_to_read(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        event = repo.create(dc_id, "question", InboxEventStatus.UNREAD)
        conn.commit()
        updated = repo.mark_read(event.id)
        assert updated is not None
        assert updated.status == InboxEventStatus.READ

    def test_noop_on_already_read(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        event = repo.create(dc_id, "question", InboxEventStatus.READ)
        conn.commit()
        updated = repo.mark_read(event.id)
        assert updated is not None
        assert updated.status == InboxEventStatus.READ

    def test_noop_on_resolved(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        event = repo.create(dc_id, "completion", InboxEventStatus.RESOLVED)
        conn.commit()
        updated = repo.mark_read(event.id)
        assert updated is not None
        assert updated.status == InboxEventStatus.RESOLVED

    def test_missing_returns_none(self, conn: sqlite3.Connection) -> None:
        assert InboxRepository(conn).mark_read("nope") is None


def _create_dc(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _seed_inbox(dc_id: str, status: InboxEventStatus = InboxEventStatus.UNREAD) -> str:
    with get_connection() as conn:
        event = InboxRepository(conn).create(dc_id, "question", status)
        conn.commit()
    return event.id


class TestReadRoute:
    def test_marks_read(self, client: TestClient) -> None:
        dc_id = _create_dc(client)
        event_id = _seed_inbox(dc_id, InboxEventStatus.UNREAD)
        resp = client.post(f"/api/v1/inbox-events/{event_id}/read")
        assert resp.status_code == 200
        assert resp.json()["status"] == "read"

    def test_noop_on_resolved(self, client: TestClient) -> None:
        dc_id = _create_dc(client)
        event_id = _seed_inbox(dc_id, InboxEventStatus.RESOLVED)
        resp = client.post(f"/api/v1/inbox-events/{event_id}/read")
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

    def test_unknown_id_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/inbox-events/nope/read")
        assert resp.status_code == 404


class TestResolveRoute:
    def test_marks_resolved(self, client: TestClient) -> None:
        dc_id = _create_dc(client)
        event_id = _seed_inbox(dc_id, InboxEventStatus.UNREAD)
        resp = client.post(f"/api/v1/inbox-events/{event_id}/resolve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

    def test_idempotent_on_resolved(self, client: TestClient) -> None:
        dc_id = _create_dc(client)
        event_id = _seed_inbox(dc_id, InboxEventStatus.RESOLVED)
        resp = client.post(f"/api/v1/inbox-events/{event_id}/resolve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

    def test_unknown_id_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/inbox-events/nope/resolve")
        assert resp.status_code == 404
