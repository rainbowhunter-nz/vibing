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


def test_init_db_records_schema_version_one(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    assert row is not None
    assert row[0] == "1"


def test_workspaces_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "workspaces")
        columns = _column_names(conn, "workspaces")
    assert columns >= {
        "id",
        "name",
        "source_type",
        "source_value",
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
        "workspace_id",
        "status",
        "started_at",
        "ended_at",
        "last_event_at",
        "created_at",
        "updated_at",
    }


def test_agent_sessions_workspace_id_has_foreign_key(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(agent_sessions)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}  # (table, from_column)
    assert ("workspaces", "workspace_id") in referenced


def test_runtime_events_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "runtime_events")
        columns = _column_names(conn, "runtime_events")
    assert columns >= {
        "id",
        "workspace_id",
        "agent_session_id",
        "event_type",
        "source",
        "payload",
        "created_at",
    }


def test_runtime_events_has_workspace_and_session_foreign_keys(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(runtime_events)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}
    assert ("workspaces", "workspace_id") in referenced
    assert ("agent_sessions", "agent_session_id") in referenced


def test_approval_requests_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "approval_requests")
        columns = _column_names(conn, "approval_requests")
    assert columns >= {
        "id",
        "workspace_id",
        "agent_session_id",
        "status",
        "requested_action",
        "created_at",
        "decided_at",
    }


def test_approval_requests_has_workspace_and_session_foreign_keys(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(approval_requests)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}
    assert ("workspaces", "workspace_id") in referenced
    assert ("agent_sessions", "agent_session_id") in referenced


def test_inbox_events_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "inbox_events")
        columns = _column_names(conn, "inbox_events")
    assert columns >= {
        "id",
        "workspace_id",
        "agent_session_id",
        "approval_request_id",
        "event_type",
        "status",
        "created_at",
        "updated_at",
    }


def test_inbox_events_has_expected_foreign_keys(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(inbox_events)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}
    assert ("workspaces", "workspace_id") in referenced
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
                "INSERT INTO agent_sessions (id, workspace_id, status, created_at, updated_at) "
                "VALUES ('s1', 'missing-ws', 'running', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
            )


def test_init_db_is_idempotent(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO workspaces (id, name, source_type, source_value, status, created_at, updated_at) "
            "VALUES ('w1', 'demo', 'local_folder', '/tmp/demo', 'created', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
    init_db()  # second run must not error or wipe data
    with get_connection() as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()
    assert count == 1


def _indexed_columns(conn, table: str) -> set[tuple[str, ...]]:
    indexes = conn.execute(f"PRAGMA index_list({table})").fetchall()
    result: set[tuple[str, ...]] = set()
    for index in indexes:
        index_name = index[1]
        info = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
        result.add(tuple(row[2] for row in info))
    return result


@pytest.mark.parametrize(
    "table,expected_columns",
    [
        ("agent_sessions", ("workspace_id",)),
        ("runtime_events", ("workspace_id", "created_at")),
        ("runtime_events", ("agent_session_id", "created_at")),
        ("inbox_events", ("workspace_id",)),
        ("inbox_events", ("status",)),
        ("approval_requests", ("status",)),
    ],
)
def test_lookup_index_exists(db_path: Path, table: str, expected_columns: tuple[str, ...]) -> None:
    init_db()
    with get_connection() as conn:
        indexes = _indexed_columns(conn, table)
    assert expected_columns in indexes, (
        f"missing index on {table}{expected_columns}; found {sorted(indexes)}"
    )
