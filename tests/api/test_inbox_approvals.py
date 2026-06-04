"""Tests for inbox-event and approval-request read APIs (VIB-39)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.core.schema import apply_schema
from vibing_api.repositories.agent_sessions import AgentSessionRepository
from vibing_api.repositories.approvals import ApprovalRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.core.vocabularies import InboxEventType
from vibing_api.repositories.inbox import InboxRepository

# ─────────────────────── repo-level fixtures ───────────────────────


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection)
    connection.commit()
    return connection


def _make_devcontainer(conn: sqlite3.Connection) -> str:
    return DevcontainerRepository(conn).create("dc", "/tmp/dc").id


def _make_session(conn: sqlite3.Connection, devcontainer_id: str) -> str:
    return AgentSessionRepository(conn).create(devcontainer_id).id


# ═══════════════════ Repository tests ═══════════════════


class TestInboxRepository:
    def test_list_all(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        e1 = repo.create(dc_id, "question", "unread")
        e2 = repo.create(dc_id, "completion", "unread")
        conn.commit()
        results = repo.list()
        assert [r.id for r in results] == [e1.id, e2.id]

    def test_list_filter_by_status(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        repo.create(dc_id, "question", "unread")
        repo.create(dc_id, "completion", "read")
        conn.commit()
        assert len(repo.list(status="unread")) == 1
        assert len(repo.list(status="read")) == 1
        assert len(repo.list(status="resolved")) == 0

    def test_list_filter_by_devcontainer(self, conn: sqlite3.Connection) -> None:
        dc1 = _make_devcontainer(conn)
        dc2 = DevcontainerRepository(conn).create("dc2", "/tmp/dc2").id
        repo = InboxRepository(conn)
        repo.create(dc1, "question", "unread")
        repo.create(dc2, "completion", "unread")
        conn.commit()
        assert len(repo.list(devcontainer_id=dc1)) == 1
        assert len(repo.list(devcontainer_id=dc2)) == 1

    def test_list_filter_by_agent_session(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        sess_id = _make_session(conn, dc_id)
        repo = InboxRepository(conn)
        repo.create(dc_id, "question", "unread", agent_session_id=sess_id)
        repo.create(dc_id, "completion", "unread")
        conn.commit()
        assert len(repo.list(agent_session_id=sess_id)) == 1
        assert len(repo.list(agent_session_id="other")) == 0

    def test_list_empty(self, conn: sqlite3.Connection) -> None:
        assert InboxRepository(conn).list() == []

    def test_get_missing_returns_none(self, conn: sqlite3.Connection) -> None:
        assert InboxRepository(conn).get("nope") is None

    def test_create_stores_content(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        created = repo.create(dc_id, "question", "unread", content="Redis or in-memory?")
        conn.commit()
        got = repo.get(created.id)
        assert got is not None
        assert got.content == "Redis or in-memory?"

    def test_create_content_defaults_none(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        created = repo.create(dc_id, "completion", "unread")
        conn.commit()
        got = repo.get(created.id)
        assert got is not None
        assert got.content is None


class TestApprovalRepository:
    def test_list_all(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        sess_id = _make_session(conn, dc_id)
        repo = ApprovalRepository(conn)
        a1 = repo.create(dc_id, sess_id, "action1")
        a2 = repo.create(dc_id, sess_id, "action2")
        conn.commit()
        results = repo.list()
        assert [r.id for r in results] == [a1.id, a2.id]

    def test_list_filter_by_status(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        sess_id = _make_session(conn, dc_id)
        repo = ApprovalRepository(conn)
        pending = repo.create(dc_id, sess_id, "do x")
        approved = repo.create(dc_id, sess_id, "do y")
        repo.resolve(approved.id, "approved")
        conn.commit()
        assert len(repo.list(status="pending")) == 1
        assert repo.list(status="pending")[0].id == pending.id
        assert len(repo.list(status="approved")) == 1
        assert len(repo.list(status="rejected")) == 0

    def test_list_filter_by_devcontainer(self, conn: sqlite3.Connection) -> None:
        dc1 = _make_devcontainer(conn)
        dc2 = DevcontainerRepository(conn).create("dc2", "/tmp/dc2").id
        sess1 = _make_session(conn, dc1)
        sess2 = _make_session(conn, dc2)
        repo = ApprovalRepository(conn)
        repo.create(dc1, sess1, "act1")
        repo.create(dc2, sess2, "act2")
        conn.commit()
        assert len(repo.list(devcontainer_id=dc1)) == 1
        assert len(repo.list(devcontainer_id=dc2)) == 1

    def test_list_empty(self, conn: sqlite3.Connection) -> None:
        assert ApprovalRepository(conn).list() == []

    def test_get_missing_returns_none(self, conn: sqlite3.Connection) -> None:
        assert ApprovalRepository(conn).get("nope") is None


# ═══════════════════ API helpers ═══════════════════


def _create_dc(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _seed_inbox(
    dc_id: str,
    event_type: InboxEventType = "question",
    status: str = "unread",
    agent_session_id: str | None = None,
    content: str | None = None,
) -> str:
    with get_connection() as conn:
        event = InboxRepository(conn).create(
            dc_id, event_type, status, agent_session_id=agent_session_id, content=content
        )
        conn.commit()
    return event.id


def _seed_approval(dc_id: str, sess_id: str, action: str = "run: migrate") -> str:
    with get_connection() as conn:
        approval = ApprovalRepository(conn).create(dc_id, sess_id, action)
        conn.commit()
    return approval.id


def _seed_session(dc_id: str) -> str:
    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(dc_id)
        conn.commit()
    return session.id


# ═══════════════════ GET /inbox-events ═══════════════════


def test_list_inbox_events_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/inbox-events")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_list_inbox_events_returns_all(client: TestClient) -> None:
    dc_id = _create_dc(client)
    _seed_inbox(dc_id, "question", "unread")
    _seed_inbox(dc_id, "completion", "read")
    resp = client.get("/api/v1/inbox-events")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_list_inbox_events_filter_status(client: TestClient) -> None:
    dc_id = _create_dc(client)
    _seed_inbox(dc_id, "question", "unread")
    _seed_inbox(dc_id, "completion", "read")
    resp = client.get("/api/v1/inbox-events?status=unread")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "unread"


def test_list_inbox_events_filter_devcontainer(client: TestClient) -> None:
    dc1 = _create_dc(client)
    dc2 = client.post("/api/v1/devcontainers", json={"name": "dc2", "local_path": "/work2"}).json()[
        "id"
    ]
    _seed_inbox(dc1, "question", "unread")
    _seed_inbox(dc2, "completion", "unread")
    resp = client.get(f"/api/v1/inbox-events?devcontainer_id={dc1}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["devcontainer_id"] == dc1


def test_list_inbox_events_filter_agent_session(client: TestClient) -> None:
    dc_id = _create_dc(client)
    sess_id = _seed_session(dc_id)
    e1 = _seed_inbox(dc_id, "question", "unread", agent_session_id=sess_id)
    _seed_inbox(dc_id, "completion", "unread")  # no session
    resp = client.get(f"/api/v1/inbox-events?agent_session_id={sess_id}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == e1


def test_list_inbox_events_response_shape(client: TestClient) -> None:
    dc_id = _create_dc(client)
    _seed_inbox(dc_id, "question", "unread")
    item = client.get("/api/v1/inbox-events").json()["items"][0]
    assert set(item.keys()) >= {
        "id",
        "devcontainer_id",
        "event_type",
        "status",
        "created_at",
        "updated_at",
    }


# ═══════════════════ GET /inbox-events/{id} ═══════════════════


def test_get_inbox_event_detail(client: TestClient) -> None:
    dc_id = _create_dc(client)
    _seed_session(dc_id)
    event_id = _seed_inbox(dc_id, "question", "unread")

    resp = client.get(f"/api/v1/inbox-events/{event_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == event_id
    assert body["devcontainer_id"] == dc_id
    assert body["devcontainer"]["id"] == dc_id
    assert body["agent_session"] is None  # no session linked
    assert body["approval_request"] is None


def test_get_inbox_event_detail_with_session_and_approval(client: TestClient) -> None:
    dc_id = _create_dc(client)
    sess_id = _seed_session(dc_id)
    approval_id = _seed_approval(dc_id, sess_id)
    with get_connection() as conn:
        event = InboxRepository(conn).create(
            dc_id,
            "approval_request",
            "unread",
            agent_session_id=sess_id,
            approval_request_id=approval_id,
        )
        conn.commit()
    event_id = event.id

    resp = client.get(f"/api/v1/inbox-events/{event_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["devcontainer"]["id"] == dc_id
    assert body["agent_session"]["id"] == sess_id
    assert body["approval_request"]["id"] == approval_id
    assert body["approval_request"]["status"] == "pending"


def test_get_inbox_event_detail_includes_content(client: TestClient) -> None:
    dc_id = _create_dc(client)
    event_id = _seed_inbox(dc_id, "question", "unread", content="Redis or in-memory?")
    resp = client.get(f"/api/v1/inbox-events/{event_id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "Redis or in-memory?"


def test_get_inbox_event_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/inbox-events/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INBOX_EVENT_NOT_FOUND"


# ═══════════════════ GET /approval-requests ═══════════════════


def test_list_approval_requests_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/approval-requests")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_list_approval_requests_returns_all(client: TestClient) -> None:
    dc_id = _create_dc(client)
    sess_id = _seed_session(dc_id)
    _seed_approval(dc_id, sess_id, "do x")
    _seed_approval(dc_id, sess_id, "do y")
    resp = client.get("/api/v1/approval-requests")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_list_approval_requests_filter_status(client: TestClient) -> None:
    dc_id = _create_dc(client)
    sess_id = _seed_session(dc_id)
    _seed_approval(dc_id, sess_id, "do x")
    ap_id = _seed_approval(dc_id, sess_id, "do y")
    with get_connection() as conn:
        ApprovalRepository(conn).resolve(ap_id, "approved")
        conn.commit()
    resp = client.get("/api/v1/approval-requests?status=pending")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "pending"


def test_list_approval_requests_filter_devcontainer(client: TestClient) -> None:
    dc1 = _create_dc(client)
    dc2 = client.post("/api/v1/devcontainers", json={"name": "dc2", "local_path": "/work2"}).json()[
        "id"
    ]
    sess1 = _seed_session(dc1)
    sess2 = _seed_session(dc2)
    _seed_approval(dc1, sess1, "act1")
    _seed_approval(dc2, sess2, "act2")
    resp = client.get(f"/api/v1/approval-requests?devcontainer_id={dc1}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["devcontainer_id"] == dc1


def test_list_approval_requests_response_shape(client: TestClient) -> None:
    dc_id = _create_dc(client)
    sess_id = _seed_session(dc_id)
    _seed_approval(dc_id, sess_id, "run: migrate")
    item = client.get("/api/v1/approval-requests").json()["items"][0]
    assert set(item.keys()) >= {
        "id",
        "devcontainer_id",
        "agent_session_id",
        "status",
        "requested_action",
        "created_at",
        "decided_at",
    }


# ═══════════════════ GET /approval-requests/{id} ═══════════════════


def test_get_approval_request_detail(client: TestClient) -> None:
    dc_id = _create_dc(client)
    sess_id = _seed_session(dc_id)
    ap_id = _seed_approval(dc_id, sess_id, "run: migrate")
    resp = client.get(f"/api/v1/approval-requests/{ap_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ap_id
    assert body["status"] == "pending"
    assert body["requested_action"] == "run: migrate"
    assert body["decided_at"] is None


def test_get_approval_request_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/approval-requests/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "APPROVAL_REQUEST_NOT_FOUND"
