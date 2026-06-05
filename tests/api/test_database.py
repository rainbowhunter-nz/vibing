import sqlite3
from pathlib import Path

import pytest

from vibing_api.core.config import settings
from vibing_api.core.database import get_connection, init_db


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "vibing-test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{path}")
    return path


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def test_init_db_creates_database_file(db_path: Path) -> None:
    assert not db_path.exists()
    init_db()
    assert db_path.exists()


def test_init_db_records_schema_version(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    assert row is not None
    assert row[0] == "4"


def test_devcontainers_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "devcontainers")
        columns = _column_names(conn, "devcontainers")
    assert columns >= {
        "id",
        "name",
        "local_path",
        "status",
        "created_at",
        "updated_at",
    }


def test_agent_sessions_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "agent_sessions")
        columns = _column_names(conn, "agent_sessions")
    assert columns >= {
        "id",
        "devcontainer_id",
        "status",
        "prompt",
        "started_at",
        "ended_at",
        "last_event_at",
        "created_at",
        "updated_at",
    }


def test_agent_sessions_devcontainer_id_has_foreign_key(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(agent_sessions)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}  # (table, from_column)
    assert ("devcontainers", "devcontainer_id") in referenced


def test_runtime_events_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "runtime_events")
        columns = _column_names(conn, "runtime_events")
    assert columns >= {
        "id",
        "devcontainer_id",
        "agent_session_id",
        "event_type",
        "source",
        "payload",
        "created_at",
    }


def test_runtime_events_has_devcontainer_and_session_foreign_keys(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(runtime_events)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}
    assert ("devcontainers", "devcontainer_id") in referenced
    assert ("agent_sessions", "agent_session_id") in referenced


def test_approval_requests_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "approval_requests")
        columns = _column_names(conn, "approval_requests")
    assert columns >= {
        "id",
        "devcontainer_id",
        "agent_session_id",
        "status",
        "requested_action",
        "created_at",
        "decided_at",
    }


def test_approval_requests_has_devcontainer_and_session_foreign_keys(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(approval_requests)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}
    assert ("devcontainers", "devcontainer_id") in referenced
    assert ("agent_sessions", "agent_session_id") in referenced


def test_inbox_events_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "inbox_events")
        columns = _column_names(conn, "inbox_events")
    assert columns >= {
        "id",
        "devcontainer_id",
        "agent_session_id",
        "approval_request_id",
        "event_type",
        "status",
        "content",
        "created_at",
        "updated_at",
    }


def test_inbox_events_has_expected_foreign_keys(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(inbox_events)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}
    assert ("devcontainers", "devcontainer_id") in referenced
    assert ("agent_sessions", "agent_session_id") in referenced
    assert ("approval_requests", "approval_request_id") in referenced


def test_session_summaries_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "session_summaries")
        columns = _column_names(conn, "session_summaries")
    assert columns >= {
        "id",
        "agent_session_id",
        "final_status",
        "started_at",
        "ended_at",
        "last_known_event",
        "summary_text",
        "created_at",
    }


def test_session_summaries_has_unique_agent_session_fk(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(session_summaries)").fetchall()
        index_list = conn.execute("PRAGMA index_list(session_summaries)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}
    assert ("agent_sessions", "agent_session_id") in referenced
    # Each session can have at most one summary.
    assert any(row[2] == 1 for row in index_list), "expected a UNIQUE index on session_summaries"


def test_get_connection_enables_foreign_keys(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        (fk_on,) = conn.execute("PRAGMA foreign_keys").fetchone()
    assert fk_on == 1


def test_foreign_keys_block_orphan_inserts(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO agent_sessions (id, devcontainer_id, status, created_at, updated_at) "
                "VALUES ('s1', 'missing-dc', 'running', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
            )


def test_init_db_is_idempotent(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO devcontainers (id, name, local_path, status, created_at, updated_at) "
            "VALUES ('dc1', 'demo', '/tmp/demo', 'created', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
    init_db()  # second run must not error or wipe data
    with get_connection() as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM devcontainers").fetchone()
    assert count == 1


def test_init_db_migrates_v2_inbox_events_adds_content_column(db_path: Path) -> None:
    """v2 DBs created before inbox content lacked the column; init_db must add it."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO app_meta (key, value) VALUES ('schema_version', '2')")
        conn.execute(
            """
            CREATE TABLE devcontainers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                local_path TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE agent_sessions (
                id TEXT PRIMARY KEY,
                devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                last_event_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE inbox_events (
                id TEXT PRIMARY KEY,
                devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
                agent_session_id TEXT REFERENCES agent_sessions(id) ON DELETE CASCADE,
                approval_request_id TEXT,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    init_db()

    with get_connection() as conn:
        assert "content" in _column_names(conn, "inbox_events")
        row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    assert row is not None
    assert row[0] == "4"


def test_fk_cascade_on_devcontainer_delete(db_path: Path) -> None:
    init_db()
    ts = "2026-01-01T00:00:00Z"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO devcontainers (id, name, local_path, status, created_at, updated_at) "
            "VALUES ('dc-cascade', 'cascade test', '/tmp/c', 'running', ?, ?)",
            (ts, ts),
        )
        conn.execute(
            "INSERT INTO agent_sessions (id, devcontainer_id, status, created_at, updated_at) "
            "VALUES ('as-cascade', 'dc-cascade', 'running', ?, ?)",
            (ts, ts),
        )
        conn.execute(
            "INSERT INTO runtime_events (id, devcontainer_id, agent_session_id, event_type, source, created_at) "
            "VALUES ('re-cascade', 'dc-cascade', 'as-cascade', 'devcontainer_started', 'host_runtime_worker', ?)",
            (ts,),
        )
        conn.execute(
            "INSERT INTO approval_requests (id, devcontainer_id, agent_session_id, status, requested_action, created_at) "
            "VALUES ('ar-cascade', 'dc-cascade', 'as-cascade', 'pending', 'run: x', ?)",
            (ts,),
        )
        conn.execute(
            "INSERT INTO inbox_events (id, devcontainer_id, agent_session_id, approval_request_id, event_type, status, created_at, updated_at) "
            "VALUES ('ie-cascade', 'dc-cascade', 'as-cascade', NULL, 'question', 'unread', ?, ?)",
            (ts, ts),
        )
        conn.commit()
        conn.execute("DELETE FROM devcontainers WHERE id = 'dc-cascade'")
        conn.commit()
        for table in ("agent_sessions", "runtime_events", "approval_requests", "inbox_events"):
            (count,) = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE devcontainer_id = 'dc-cascade'"
            ).fetchone()
            assert count == 0, f"cascade failed: {table} still has rows after devcontainer delete"
