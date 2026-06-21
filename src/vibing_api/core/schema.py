"""Raw SQLite schema for the Vibing MVP persistence layer.

Keep this file the single source of truth for the on-disk shape.
"""

import sqlite3

SCHEMA_VERSION = "8"

_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS devcontainers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        local_path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS harness_credentials (
        name TEXT PRIMARY KEY,
        blob TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS delegated_runs (
        devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
        run_id TEXT NOT NULL,
        harness TEXT NOT NULL,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        result TEXT,
        error TEXT,
        started_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (devcontainer_id, run_id)
    )
    """,
)

_INDEX_STATEMENTS: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_delegated_runs_devcontainer ON delegated_runs(devcontainer_id)",
)


def _drop_legacy(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS harness_status")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(devcontainers)")}
    if "status" in cols:
        conn.execute("ALTER TABLE devcontainers DROP COLUMN status")


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Record schema version."""
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SCHEMA_VERSION,),
    )


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create tables, indexes, migrate, and record schema metadata. Idempotent."""
    for statement in _TABLE_STATEMENTS:
        conn.execute(statement)
    for statement in _INDEX_STATEMENTS:
        conn.execute(statement)
    _drop_legacy(conn)
    _migrate_schema(conn)


def read_schema_version(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    return row[0] if row is not None else None
