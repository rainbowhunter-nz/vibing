from pathlib import Path

import pytest
from vibing_protocol.runtime_events import InvalidRuntimeEventError

from vibing_api.core.database import get_connection, init_db
from vibing_api.repositories.runtime_events import RuntimeEventRepository


@pytest.fixture
def initialized_db(db_path: Path) -> Path:
    init_db()
    return db_path


def _insert_devcontainer(conn, devcontainer_id: str) -> None:
    conn.execute(
        "INSERT INTO devcontainers "
        "(id, name, local_path, status, created_at, updated_at) "
        "VALUES (?, ?, '/tmp/x', 'created', "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
        (devcontainer_id, devcontainer_id),
    )


def _insert_session(conn, session_id: str, devcontainer_id: str) -> None:
    conn.execute(
        "INSERT INTO agent_sessions (id, devcontainer_id, status, created_at, updated_at) "
        "VALUES (?, ?, 'running', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
        (session_id, devcontainer_id),
    )


def test_user_input_sent_in_event_vocabulary() -> None:
    from vibing_protocol.runtime_events import EVENT_TYPES, RuntimeEvent

    assert "user_input_sent" in EVENT_TYPES
    evt = RuntimeEvent(
        event_type="user_input_sent",
        source="devcontainer_runtime_agent",
        devcontainer_id="dc-1",
        agent_session_id="sess-1",
        payload={"inbox_event_id": "inbox-42"},
    )
    assert evt.event_type == "user_input_sent"


def test_record_runtime_event_persists_row(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_devcontainer(conn, "dc1")
        conn.commit()
        event = RuntimeEventRepository(conn).record(
            event_type="devcontainer_started",
            source="host_runtime_worker",
            devcontainer_id="dc1",
        )
        conn.commit()

    assert event.event_type == "devcontainer_started"
    assert event.source == "host_runtime_worker"
    assert event.devcontainer_id == "dc1"
    assert event.agent_session_id is None
    assert event.payload is None
    assert event.id
    assert event.created_at


def test_record_runtime_event_round_trips_payload(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_devcontainer(conn, "dc1")
        _insert_session(conn, "s1", "dc1")
        conn.commit()
        repo = RuntimeEventRepository(conn)
        recorded = repo.record(
            event_type="agent_asked_question",
            source="devcontainer_runtime_agent",
            devcontainer_id="dc1",
            agent_session_id="s1",
            payload={"question": "ok?"},
        )
        conn.commit()

        events = repo.list_by_session("s1")

    assert len(events) == 1
    assert events[0].id == recorded.id
    assert events[0].payload == {"question": "ok?"}


def test_record_runtime_event_rejects_unknown_event_type(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_devcontainer(conn, "dc1")
        conn.commit()
        with pytest.raises(InvalidRuntimeEventError):
            RuntimeEventRepository(conn).record(
                event_type="not_a_real_event",  # type: ignore[arg-type]
                source="host_runtime_worker",
                devcontainer_id="dc1",
            )


def test_record_runtime_event_rejects_unknown_source(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_devcontainer(conn, "dc1")
        conn.commit()
        with pytest.raises(InvalidRuntimeEventError):
            RuntimeEventRepository(conn).record(
                event_type="devcontainer_started",
                source="bogus_source",  # type: ignore[arg-type]
                devcontainer_id="dc1",
            )


def test_list_runtime_events_by_devcontainer_filters_and_orders(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_devcontainer(conn, "dc1")
        _insert_devcontainer(conn, "dc2")
        conn.commit()
        repo = RuntimeEventRepository(conn)
        first = repo.record(
            event_type="devcontainer_started",
            source="host_runtime_worker",
            devcontainer_id="dc1",
        )
        repo.record(
            event_type="devcontainer_failed",
            source="host_runtime_worker",
            devcontainer_id="dc2",
        )
        second = repo.record(
            event_type="devcontainer_failed",
            source="host_runtime_worker",
            devcontainer_id="dc1",
        )
        conn.commit()

        events = repo.list_by_devcontainer("dc1")

    assert [e.id for e in events] == [first.id, second.id]
    assert all(e.devcontainer_id == "dc1" for e in events)


def test_list_runtime_events_by_session_filters_and_orders(initialized_db: Path) -> None:
    with get_connection() as conn:
        _insert_devcontainer(conn, "dc1")
        _insert_session(conn, "s1", "dc1")
        _insert_session(conn, "s2", "dc1")
        conn.commit()
        repo = RuntimeEventRepository(conn)
        first = repo.record(
            event_type="agent_session_started",
            source="devcontainer_runtime_agent",
            devcontainer_id="dc1",
            agent_session_id="s1",
        )
        repo.record(
            event_type="agent_session_started",
            source="devcontainer_runtime_agent",
            devcontainer_id="dc1",
            agent_session_id="s2",
        )
        second = repo.record(
            event_type="session_completed",
            source="devcontainer_runtime_agent",
            devcontainer_id="dc1",
            agent_session_id="s1",
        )
        conn.commit()

        events = repo.list_by_session("s1")

    assert [e.id for e in events] == [first.id, second.id]
    assert all(e.agent_session_id == "s1" for e in events)
