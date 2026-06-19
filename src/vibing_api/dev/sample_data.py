"""Local-development sample data for product UI validation.

Inserts a curated, deterministic set of devcontainers. Every sample row has an id
prefixed with `sample-` and every sample devcontainer name starts with `[sample] `
so rows are visible in the UI and removable in a single DELETE per table.
Not part of the production import graph.
"""

import sqlite3

SAMPLE_ID_PREFIX = "sample-"
SAMPLE_NAME_PREFIX = "[sample] "
FIXED_TS = "2026-01-01T12:00:00+00:00"

SAMPLE_DEVCONTAINERS: tuple[dict, ...] = (
    {
        "id": "sample-dc-web",
        "name": "[sample] vibing-web",
        "local_path": "/sample/projects/vibing-web",
        "status": "running",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-dc-api",
        "name": "[sample] vibing-api",
        "local_path": "/sample/projects/vibing-api",
        "status": "stopped",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
    {
        "id": "sample-dc-cli",
        "name": "[sample] vibing-cli",
        "local_path": "/sample/projects/vibing-cli",
        "status": "error",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
)

# Insert order = top to bottom. Reset order = reverse of this.
_DATASET: tuple[tuple[str, tuple[dict, ...]], ...] = (("devcontainers", SAMPLE_DEVCONTAINERS),)


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
