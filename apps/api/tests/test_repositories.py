import sqlite3

import pytest

from vibing_api.core.schema import apply_schema
from vibing_api.repositories.agent_sessions import AgentSessionRepository
from vibing_api.repositories.approvals import ApprovalRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.inbox import InboxRepository
from vibing_api.repositories.runtime_events import RuntimeEventRepository
from vibing_api.repositories.summaries import SessionSummaryRepository


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection)
    connection.commit()
    return connection


def _make_devcontainer(conn: sqlite3.Connection) -> str:
    dc = DevcontainerRepository(conn).create("dc", "/tmp/dc")
    return dc.id


def _make_session(conn: sqlite3.Connection, devcontainer_id: str) -> str:
    return AgentSessionRepository(conn).create(devcontainer_id).id


def test_devcontainer_round_trip(conn: sqlite3.Connection) -> None:
    repo = DevcontainerRepository(conn)
    created = repo.create("web", "/projects/web")
    fetched = repo.get(created.id)
    assert fetched == created
    assert fetched.status == "created"
    assert repo.list() == [created]


def test_devcontainer_update_only_provided_fields(conn: sqlite3.Connection) -> None:
    repo = DevcontainerRepository(conn)
    created = repo.create("web", "/projects/web")
    updated = repo.update(created.id, status="running")
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


def test_agent_session_round_trip(conn: sqlite3.Connection) -> None:
    dc_id = _make_devcontainer(conn)
    repo = AgentSessionRepository(conn)
    created = repo.create(dc_id, status="running")
    fetched = repo.get(created.id)
    assert fetched == created
    assert fetched.devcontainer_id == dc_id
    assert fetched.status == "running"


def test_approval_round_trip(conn: sqlite3.Connection) -> None:
    dc_id = _make_devcontainer(conn)
    session_id = _make_session(conn, dc_id)
    repo = ApprovalRepository(conn)
    created = repo.create(dc_id, session_id, "run: migrate")
    fetched = repo.get(created.id)
    assert fetched == created
    assert fetched.status == "pending"
    assert fetched.requested_action == "run: migrate"


def test_inbox_round_trip(conn: sqlite3.Connection) -> None:
    dc_id = _make_devcontainer(conn)
    session_id = _make_session(conn, dc_id)
    repo = InboxRepository(conn)
    created = repo.create(dc_id, "question", "unread", agent_session_id=session_id)
    fetched = repo.get(created.id)
    assert fetched == created
    assert fetched.event_type == "question"
    assert fetched.status == "unread"


def test_summary_round_trip(conn: sqlite3.Connection) -> None:
    dc_id = _make_devcontainer(conn)
    session_id = _make_session(conn, dc_id)
    repo = SessionSummaryRepository(conn)
    created = repo.create(session_id, "completed", summary_text="done")
    assert repo.get(created.id) == created
    assert repo.get_by_session(session_id) == created


def test_devcontainer_delete_cascades(conn: sqlite3.Connection) -> None:
    dc_id = _make_devcontainer(conn)
    session_id = _make_session(conn, dc_id)
    approval = ApprovalRepository(conn).create(dc_id, session_id, "run: x")
    inbox = InboxRepository(conn).create(dc_id, "question", "unread", agent_session_id=session_id)
    event = RuntimeEventRepository(conn).record(
        event_type="devcontainer_started",
        source="host_runtime_worker",
        devcontainer_id=dc_id,
    )

    assert DevcontainerRepository(conn).delete(dc_id) is True

    assert AgentSessionRepository(conn).get(session_id) is None
    assert ApprovalRepository(conn).get(approval.id) is None
    assert InboxRepository(conn).get(inbox.id) is None
    assert RuntimeEventRepository(conn).list_by_devcontainer(dc_id) == []
    assert event.devcontainer_id == dc_id
