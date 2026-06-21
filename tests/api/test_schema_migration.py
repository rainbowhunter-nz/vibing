import sqlite3

from vibing_api.core.schema import apply_schema


def test_devcontainers_has_no_status_column(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "t.db")
    apply_schema(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(devcontainers)")}
    assert cols == {"id", "name", "local_path", "created_at", "updated_at"}


def test_harness_status_table_removed(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "t.db")
    apply_schema(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "harness_status" not in tables


def test_migration_drops_legacy_status_and_table(tmp_path) -> None:
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE devcontainers (id TEXT PRIMARY KEY, name TEXT, local_path TEXT, "
        "status TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.execute("CREATE TABLE harness_status (devcontainer_id TEXT, name TEXT)")
    conn.commit()
    apply_schema(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(devcontainers)")}
    assert "status" not in cols
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "harness_status" not in tables
