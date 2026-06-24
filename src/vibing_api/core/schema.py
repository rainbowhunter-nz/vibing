"""Raw SQLite schema for the Vibing MVP persistence layer.

Keep this file the single source of truth for the on-disk shape.
"""

import sqlite3

SCHEMA_VERSION = "9"

# delegated_runs is a read-model projection keyed by devcontainer_id, which may be a
# discovered (virtual, never-persisted) id — so it carries NO FK to devcontainers.
_DELEGATED_RUNS_DDL = """
    CREATE TABLE IF NOT EXISTS delegated_runs (
        devcontainer_id TEXT NOT NULL,
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
    """

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
    _DELEGATED_RUNS_DDL,
)

_INDEX_STATEMENTS: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_delegated_runs_devcontainer ON delegated_runs(devcontainer_id)",
)


def _drop_legacy(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("DROP TABLE IF EXISTS harness_status")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(devcontainers)")}
        if "status" in cols:
            conn.execute("ALTER TABLE devcontainers DROP COLUMN status")


def _drop_delegated_runs_fk(conn: sqlite3.Connection) -> None:
    """Rebuild delegated_runs without its legacy FK so discovered-devcontainer runs persist."""
    if not conn.execute("PRAGMA foreign_key_list(delegated_runs)").fetchall():
        return
    conn.executescript(
        "ALTER TABLE delegated_runs RENAME TO _delegated_runs_old;"
        f"{_DELEGATED_RUNS_DDL};"
        "INSERT INTO delegated_runs SELECT * FROM _delegated_runs_old;"
        "DROP TABLE _delegated_runs_old;"
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
    _drop_delegated_runs_fk(conn)
    for statement in _INDEX_STATEMENTS:
        conn.execute(statement)
    _migrate_schema(conn)


def read_schema_version(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    return row[0] if row is not None else None
