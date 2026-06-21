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
    assert row[0] == "8"


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


def test_foreign_keys_block_orphan_inserts(db_path: Path) -> None:
    init_db()
    ts = "2026-01-01T00:00:00Z"
    with get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO delegated_runs "
                "(devcontainer_id, run_id, harness, model, status, started_at, updated_at) "
                "VALUES ('missing-dc', 'run-1', 'gh', 'gpt4', 'running', ?, ?)",
                (ts, ts),
            )


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


def test_fk_cascade_on_devcontainer_delete(db_path: Path) -> None:
    init_db()
    ts = "2026-01-01T00:00:00Z"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO devcontainers (id, name, local_path, created_at, updated_at) "
            "VALUES ('dc-cascade', 'cascade test', '/tmp/c', ?, ?)",
            (ts, ts),
        )
        conn.execute(
            "INSERT INTO delegated_runs "
            "(devcontainer_id, run_id, harness, model, status, started_at, updated_at) "
            "VALUES ('dc-cascade', 'run-1', 'gh', 'gpt4', 'running', ?, ?)",
            (ts, ts),
        )
        conn.commit()
        conn.execute("DELETE FROM devcontainers WHERE id = 'dc-cascade'")
        conn.commit()
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM delegated_runs WHERE devcontainer_id = 'dc-cascade'"
        ).fetchone()
        assert count == 0, "cascade failed: delegated_runs still has rows after devcontainer delete"
