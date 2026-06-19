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
    assert tables == {"app_meta", "devcontainers", "harness_status", "harness_credentials"}


def test_init_db_creates_database_file(db_path: Path) -> None:
    assert not db_path.exists()
    init_db()
    assert db_path.exists()


def test_init_db_records_schema_version(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    assert row is not None
    assert row[0] == "6"


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


def test_harness_status_table_exists_with_required_columns(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        assert _table_exists(conn, "harness_status")
        columns = _column_names(conn, "harness_status")
    assert columns >= {
        "devcontainer_id",
        "name",
        "installed",
        "authenticated",
        "updated_at",
    }


def test_harness_status_has_devcontainer_foreign_key(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(harness_status)").fetchall()
    referenced = {(row[2], row[3]) for row in fks}
    assert ("devcontainers", "devcontainer_id") in referenced


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
                "INSERT INTO harness_status (devcontainer_id, name, installed, authenticated, updated_at) "
                "VALUES ('missing-dc', 'claude-code', 1, 0, ?)",
                (ts,),
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
            "INSERT INTO harness_status (devcontainer_id, name, installed, authenticated, updated_at) "
            "VALUES ('dc-cascade', 'claude-code', 1, 1, ?)",
            (ts,),
        )
        conn.commit()
        conn.execute("DELETE FROM devcontainers WHERE id = 'dc-cascade'")
        conn.commit()
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM harness_status WHERE devcontainer_id = 'dc-cascade'"
        ).fetchone()
        assert count == 0, "cascade failed: harness_status still has rows after devcontainer delete"
