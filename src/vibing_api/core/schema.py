"""Raw SQLite schema for the Vibing MVP persistence layer.

Keep this file the single source of truth for the on-disk shape.
"""

import sqlite3

SCHEMA_VERSION = "3"

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
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_sessions (
        id TEXT PRIMARY KEY,
        devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        started_at TEXT,
        ended_at TEXT,
        last_event_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_events (
        id TEXT PRIMARY KEY,
        devcontainer_id TEXT REFERENCES devcontainers(id) ON DELETE CASCADE,
        agent_session_id TEXT REFERENCES agent_sessions(id) ON DELETE CASCADE,
        event_type TEXT NOT NULL,
        source TEXT NOT NULL,
        payload TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS approval_requests (
        id TEXT PRIMARY KEY,
        devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
        agent_session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
        status TEXT NOT NULL,
        requested_action TEXT NOT NULL,
        created_at TEXT NOT NULL,
        decided_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inbox_events (
        id TEXT PRIMARY KEY,
        devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
        agent_session_id TEXT REFERENCES agent_sessions(id) ON DELETE CASCADE,
        approval_request_id TEXT REFERENCES approval_requests(id) ON DELETE SET NULL,
        event_type TEXT NOT NULL,
        status TEXT NOT NULL,
        content TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_summaries (
        id TEXT PRIMARY KEY,
        agent_session_id TEXT NOT NULL UNIQUE
            REFERENCES agent_sessions(id) ON DELETE CASCADE,
        final_status TEXT NOT NULL,
        started_at TEXT,
        ended_at TEXT,
        last_known_event TEXT,
        summary_text TEXT,
        created_at TEXT NOT NULL
    )
    """,
)

_INDEX_STATEMENTS: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_agent_sessions_devcontainer ON agent_sessions(devcontainer_id)",
    "CREATE INDEX IF NOT EXISTS idx_runtime_events_devcontainer_created "
    "ON runtime_events(devcontainer_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_runtime_events_session_created "
    "ON runtime_events(agent_session_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_inbox_events_devcontainer ON inbox_events(devcontainer_id)",
    "CREATE INDEX IF NOT EXISTS idx_inbox_events_status ON inbox_events(status)",
    "CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON approval_requests(status)",
)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Create tables, indexes, and seed schema metadata. Idempotent."""
    for statement in _TABLE_STATEMENTS:
        conn.execute(statement)
    for statement in _INDEX_STATEMENTS:
        conn.execute(statement)
    conn.execute(
        "INSERT OR IGNORE INTO app_meta (key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )


def read_schema_version(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
    return row[0] if row is not None else None
