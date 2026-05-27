"""Local-development sample data for product UI validation.

Inserts a curated, deterministic set of workspaces, agent sessions,
approval requests, and inbox events. Every sample row has an id
prefixed with `sample-` and every sample workspace name starts with
`[sample] ` so rows are visible in the UI and removable in a single
DELETE per table. Not part of the production import graph.
"""

import argparse
import sqlite3
import sys

from vibing_api.core.database import get_connection, init_db

SAMPLE_ID_PREFIX = "sample-"
SAMPLE_NAME_PREFIX = "[sample] "
FIXED_TS = "2026-01-01T12:00:00+00:00"

SAMPLE_WORKSPACES: tuple[dict, ...] = (
    {
        "id": "sample-ws-web",
        "name": "[sample] vibing-web",
        "source_type": "local_folder",
        "source_value": "/sample/projects/vibing-web",
        "status": "running",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-ws-api",
        "name": "[sample] vibing-api",
        "source_type": "local_folder",
        "source_value": "/sample/projects/vibing-api",
        "status": "stopped",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-ws-cli",
        "name": "[sample] vibing-cli",
        "source_type": "local_folder",
        "source_value": "/sample/projects/vibing-cli",
        "status": "error",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
)

SAMPLE_AGENT_SESSIONS: tuple[dict, ...] = (
    {
        "id": "sample-as-web",
        "workspace_id": "sample-ws-web",
        "status": "running",
        "started_at": FIXED_TS,
        "ended_at": None,
        "last_event_at": FIXED_TS,
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-as-api",
        "workspace_id": "sample-ws-api",
        "status": "waiting_for_approval",
        "started_at": FIXED_TS,
        "ended_at": None,
        "last_event_at": FIXED_TS,
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-as-cli",
        "workspace_id": "sample-ws-cli",
        "status": "completed",
        "started_at": FIXED_TS,
        "ended_at": FIXED_TS,
        "last_event_at": FIXED_TS,
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
)

SAMPLE_APPROVAL_REQUESTS: tuple[dict, ...] = (
    {
        "id": "sample-ar-001",
        "workspace_id": "sample-ws-api",
        "agent_session_id": "sample-as-api",
        "status": "pending",
        "requested_action": "run: pnpm migrate",
        "created_at": FIXED_TS,
        "decided_at": None,
    },
    {
        "id": "sample-ar-002",
        "workspace_id": "sample-ws-web",
        "agent_session_id": "sample-as-web",
        "status": "approved",
        "requested_action": "run: rm node_modules",
        "created_at": FIXED_TS,
        "decided_at": FIXED_TS,
    },
)

SAMPLE_INBOX_EVENTS: tuple[dict, ...] = (
    {
        "id": "sample-ie-001",
        "workspace_id": "sample-ws-api",
        "agent_session_id": "sample-as-api",
        "approval_request_id": None,
        "event_type": "question",
        "status": "unread",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-ie-002",
        "workspace_id": "sample-ws-api",
        "agent_session_id": "sample-as-api",
        "approval_request_id": "sample-ar-001",
        "event_type": "approval_request",
        "status": "unread",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-ie-003",
        "workspace_id": "sample-ws-cli",
        "agent_session_id": "sample-as-cli",
        "approval_request_id": None,
        "event_type": "failure",
        "status": "read",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-ie-004",
        "workspace_id": "sample-ws-cli",
        "agent_session_id": "sample-as-cli",
        "approval_request_id": None,
        "event_type": "completion",
        "status": "resolved",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
)

# Insert order = top to bottom (parents before children for foreign keys).
# Reset order = reverse of this.
_DATASET: tuple[tuple[str, tuple[dict, ...]], ...] = (
    ("workspaces", SAMPLE_WORKSPACES),
    ("agent_sessions", SAMPLE_AGENT_SESSIONS),
    ("approval_requests", SAMPLE_APPROVAL_REQUESTS),
    ("inbox_events", SAMPLE_INBOX_EVENTS),
)


def seed(conn: sqlite3.Connection) -> int:
    """Insert the curated sample dataset.

    Calls `reset(conn)` first so re-seeding is idempotent. Caller is
    responsible for `conn.commit()`. Returns the number of inserted rows.
    """
    reset(conn)
    inserted = 0
    for table, rows in _DATASET:
        for row in rows:
            columns = ", ".join(row.keys())
            placeholders = ", ".join("?" for _ in row)
            conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                tuple(row.values()),
            )
            inserted += 1
    return inserted


def reset(conn: sqlite3.Connection) -> int:
    """Delete all rows whose id starts with `sample-`.

    Runs in reverse insert order to keep FK cascades quiet. Caller is
    responsible for `conn.commit()`. Returns the number of removed rows.
    """
    removed = 0
    for table, _ in reversed(_DATASET):
        cursor = conn.execute(
            f"DELETE FROM {table} WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        )
        removed += cursor.rowcount
    return removed


def status(conn: sqlite3.Connection) -> dict[str, int]:
    """Return per-table counts of rows with the sample id prefix."""
    counts: dict[str, int] = {}
    for table, _ in _DATASET:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()
        counts[table] = row[0]
    return counts


def _cmd_seed() -> int:
    init_db()
    with get_connection() as conn:
        inserted = seed(conn)
        conn.commit()
    print(f"seeded {inserted} rows across {len(_DATASET)} tables.")
    return 0


def _cmd_reset() -> int:
    init_db()
    with get_connection() as conn:
        removed = reset(conn)
        conn.commit()
    print(f"removed {removed} sample rows.")
    return 0


def _cmd_status() -> int:
    init_db()
    with get_connection() as conn:
        counts = status(conn)
    for table, _ in _DATASET:
        print(f"{table}: {counts[table]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m vibing_api.dev.sample_data",
        description="Seed, reset, or report on local sample data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="Insert the curated sample dataset.")
    subparsers.add_parser("reset", help="Remove all sample-prefixed rows.")
    subparsers.add_parser("status", help="Print per-table sample row counts.")
    args = parser.parse_args(argv)
    if args.command == "seed":
        return _cmd_seed()
    if args.command == "reset":
        return _cmd_reset()
    if args.command == "status":
        return _cmd_status()
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
