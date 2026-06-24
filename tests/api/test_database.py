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


def test_schema_has_expected_tables(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:")
    from vibing_api.core.schema import apply_schema

    apply_schema(conn)
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert tables == {
        "app_meta",
        "devcontainers",
        "harness_credentials",
        "delegated_runs",
    }


def test_init_db_creates_database_file(db_path: Path) -> None:
    assert not db_path.exists()
    init_db()
    assert db_path.exists()


def test_init_db_records_schema_version(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    assert row is not None
    assert row[0] == "9"


def test_devcontainers_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "devcontainers")
        columns = _column_names(conn, "devcontainers")
    assert columns >= {"id", "name", "local_path", "created_at", "updated_at"}
    assert "status" not in columns


def test_get_connection_enables_foreign_keys(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        (fk_on,) = conn.execute("PRAGMA foreign_keys").fetchone()
    assert fk_on == 1


def test_delegated_runs_accepts_unpersisted_devcontainer(db_path: Path) -> None:
    """Discovered devcontainers are virtual (never persisted) — their runs must still store."""
    init_db()
    ts = "2026-01-01T00:00:00Z"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO delegated_runs "
            "(devcontainer_id, run_id, harness, model, status, started_at, updated_at) "
            "VALUES ('discovered-dc', 'run-1', 'gh', 'gpt4', 'running', ?, ?)",
            (ts, ts),
        )
        conn.commit()
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM delegated_runs WHERE devcontainer_id = 'discovered-dc'"
        ).fetchone()
    assert count == 1


def test_init_db_is_idempotent(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO devcontainers (id, name, local_path, created_at, updated_at) "
            "VALUES ('dc1', 'demo', '/tmp/demo', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
    init_db()  # second run must not error or wipe data
    with get_connection() as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM devcontainers").fetchone()
    assert count == 1


def test_migrates_legacy_delegated_runs_fk(db_path: Path) -> None:
    """A pre-existing delegated_runs with the legacy FK is rebuilt without it, preserving rows."""
    ts = "2026-01-01T00:00:00Z"
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE devcontainers (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "local_path TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE delegated_runs ("
            "devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE, "
            "run_id TEXT NOT NULL, harness TEXT NOT NULL, model TEXT NOT NULL, "
            "status TEXT NOT NULL, result TEXT, error TEXT, started_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, PRIMARY KEY (devcontainer_id, run_id))"
        )
        conn.execute(
            "INSERT INTO devcontainers (id, name, local_path, created_at, updated_at) "
            "VALUES ('dc1', 'd', '/tmp/d', ?, ?)",
            (ts, ts),
        )
        conn.execute(
            "INSERT INTO delegated_runs "
            "(devcontainer_id, run_id, harness, model, status, started_at, updated_at) "
            "VALUES ('dc1', 'run-1', 'gh', 'gpt4', 'running', ?, ?)",
            (ts, ts),
        )
        conn.commit()

    init_db()  # migration drops the FK, preserves the row

    with get_connection() as conn:
        assert conn.execute("PRAGMA foreign_key_list(delegated_runs)").fetchall() == []
        conn.execute(
            "INSERT INTO delegated_runs "
            "(devcontainer_id, run_id, harness, model, status, started_at, updated_at) "
            "VALUES ('discovered-dc', 'run-2', 'gh', 'gpt4', 'running', ?, ?)",
            (ts, ts),
        )
        conn.commit()
        run_ids = {r[0] for r in conn.execute("SELECT run_id FROM delegated_runs")}
    assert run_ids == {"run-1", "run-2"}
