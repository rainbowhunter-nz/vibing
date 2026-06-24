"""Raw SQLite schema for the Vibing MVP persistence layer.

Keep this file the single source of truth for the on-disk shape.
"""

import sqlite3

SCHEMA_VERSION = "9"

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
        local_path TEXT NOT NULL UNIQUE,
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
)

_INDEX_STATEMENTS: tuple[str, ...] = ()


def _drop_legacy(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("DROP TABLE IF EXISTS harness_status")
        conn.execute("DROP TABLE IF EXISTS delegated_runs")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(devcontainers)")}
        if "status" in cols:
            conn.execute("ALTER TABLE devcontainers DROP COLUMN status")


def _migrate_devcontainers_unique_path(conn: sqlite3.Connection) -> None:
    """Add UNIQUE(local_path); dedup existing rows (keep oldest created_at) first."""
    indexes = conn.execute("PRAGMA index_list(devcontainers)").fetchall()
    has_unique_path = any(
        row[2]  # unique flag
        and any(c[2] == "local_path" for c in conn.execute(f"PRAGMA index_info({row[1]})"))
        for row in indexes
    )
    if has_unique_path:
        return
    conn.executescript(
        "DELETE FROM devcontainers WHERE id NOT IN ("
        "  SELECT id FROM devcontainers d WHERE created_at = ("
        "    SELECT MIN(created_at) FROM devcontainers WHERE local_path = d.local_path)"
        "  GROUP BY local_path);"
        "ALTER TABLE devcontainers RENAME TO _devcontainers_old;"
        "CREATE TABLE devcontainers (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "local_path TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
        "INSERT INTO devcontainers SELECT id, name, local_path, created_at, updated_at "
        "FROM _devcontainers_old;"
        "DROP TABLE _devcontainers_old;"
    )


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
    _drop_legacy(conn)
    _migrate_devcontainers_unique_path(conn)
    for statement in _INDEX_STATEMENTS:
        conn.execute(statement)
    _migrate_schema(conn)


def read_schema_version(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    return row[0] if row is not None else None
