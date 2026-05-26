from pathlib import Path

import pytest

from vibing_api.core.commands import COMMAND_TYPES
from vibing_api.core.database import get_connection, init_db
from vibing_api.core.runtime_events import (
    EVENT_TYPES,
    RUNTIME_EVENT_SOURCES,
    InvalidRuntimeEventError,
    list_runtime_events_by_session,
    list_runtime_events_by_workspace,
    record_runtime_event,
)


@pytest.fixture
def initialized_db(db_path: Path) -> Path:
    init_db()
    return db_path


def _insert_workspace(conn, workspace_id: str) -> None:
    conn.execute(
        "INSERT INTO workspaces "
        "(id, name, source_type, source_value, status, created_at, updated_at) "
        "VALUES (?, ?, 'local_folder', '/tmp/x', 'created', "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
        (workspace_id, workspace_id),
    )


def _insert_session(conn, session_id: str, workspace_id: str) -> None:
    conn.execute(
        "INSERT INTO agent_sessions (id, workspace_id, status, created_at, updated_at) "
        "VALUES (?, ?, 'running', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
        (session_id, workspace_id),
    )



def test_record_runtime_event_persists_row(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_workspace(conn, "ws1")
        conn.commit()
        event = record_runtime_event(
            conn,
            event_type="workspace_started",
            source="host_runtime_worker",
            workspace_id="ws1",
        )
        conn.commit()

    assert event.event_type == "workspace_started"
    assert event.source == "host_runtime_worker"
    assert event.workspace_id == "ws1"
    assert event.agent_session_id is None
    assert event.payload is None
    assert event.id
    assert event.created_at


def test_record_runtime_event_round_trips_payload(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_workspace(conn, "ws1")
        _insert_session(conn, "s1", "ws1")
        conn.commit()
        recorded = record_runtime_event(
            conn,
            event_type="claude_asked_question",
            source="workspace_runtime_agent",
            workspace_id="ws1",
            agent_session_id="s1",
            payload={"question": "ok?"},
        )
        conn.commit()

        events = list_runtime_events_by_session(conn, "s1")

    assert len(events) == 1
    assert events[0].id == recorded.id
    assert events[0].payload == {"question": "ok?"}


def test_record_runtime_event_rejects_unknown_event_type(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_workspace(conn, "ws1")
        conn.commit()
        with pytest.raises(InvalidRuntimeEventError):
            record_runtime_event(
                conn,
                event_type="not_a_real_event",  # type: ignore[arg-type]
                source="host_runtime_worker",
                workspace_id="ws1",
            )


def test_record_runtime_event_rejects_unknown_source(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_workspace(conn, "ws1")
        conn.commit()
        with pytest.raises(InvalidRuntimeEventError):
            record_runtime_event(
                conn,
                event_type="workspace_started",
                source="bogus_source",  # type: ignore[arg-type]
                workspace_id="ws1",
            )


def test_list_runtime_events_by_workspace_filters_and_orders(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_workspace(conn, "ws1")
        _insert_workspace(conn, "ws2")
        conn.commit()
        first = record_runtime_event(
            conn,
            event_type="workspace_started",
            source="host_runtime_worker",
            workspace_id="ws1",
        )
        record_runtime_event(
            conn,
            event_type="workspace_failed",
            source="host_runtime_worker",
            workspace_id="ws2",
        )
        second = record_runtime_event(
            conn,
            event_type="workspace_failed",
            source="host_runtime_worker",
            workspace_id="ws1",
        )
        conn.commit()

        events = list_runtime_events_by_workspace(conn, "ws1")

    assert [e.id for e in events] == [first.id, second.id]
    assert all(e.workspace_id == "ws1" for e in events)


def test_list_runtime_events_by_session_filters_and_orders(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_workspace(conn, "ws1")
        _insert_session(conn, "s1", "ws1")
        _insert_session(conn, "s2", "ws1")
        conn.commit()
        first = record_runtime_event(
            conn,
            event_type="claude_session_started",
            source="workspace_runtime_agent",
            workspace_id="ws1",
            agent_session_id="s1",
        )
        record_runtime_event(
            conn,
            event_type="claude_session_started",
            source="workspace_runtime_agent",
            workspace_id="ws1",
            agent_session_id="s2",
        )
        second = record_runtime_event(
            conn,
            event_type="session_completed",
            source="workspace_runtime_agent",
            workspace_id="ws1",
            agent_session_id="s1",
        )
        conn.commit()

        events = list_runtime_events_by_session(conn, "s1")

    assert [e.id for e in events] == [first.id, second.id]
    assert all(e.agent_session_id == "s1" for e in events)
