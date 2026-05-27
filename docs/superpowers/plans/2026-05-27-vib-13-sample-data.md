# VIB-13 Sample Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dev-only `python -m vibing_api.dev.sample_data {seed,reset,status}` command that seeds, resets, and reports on a curated set of sample workspaces, agent sessions, inbox events, and approval requests so the dashboard, inbox, and approval queue can be validated before the real runtime exists.

**Architecture:** New `apps/api/src/vibing_api/dev/` package containing a single feature file `sample_data.py`. That file holds module-level dataset constants, three pure helpers (`seed`, `reset`, `status`) that take a `sqlite3.Connection`, and an argparse `main()`. Every sample row's `id` starts with `sample-` and every sample workspace `name` starts with `[sample] ` so the rows are obvious in the UI and removable in one DELETE per table. Reset runs in reverse insert order so foreign-key cascades never need to fire mid-transaction. Tests use the existing `db_path` fixture; one HTTP smoke test reuses the `client` fixture.

**Tech Stack:** Python 3.13, sqlite3 (stdlib), argparse (stdlib), pydantic, FastAPI, pytest, uv. Spec: `docs/superpowers/specs/2026-05-27-vib-13-sample-data-design.md`. Domain vocabulary: `docs/domain-model.md`. DB schema: `apps/api/src/vibing_api/core/schema.py`.

---

## File Structure

**Created**

- `apps/api/src/vibing_api/dev/__init__.py` — empty marker.
- `apps/api/src/vibing_api/dev/sample_data.py` — the entire feature: constants, helpers, argparse main.
- `apps/api/tests/test_sample_data.py` — pytest tests for the helpers, the CLI, and an HTTP smoke check.

**Modified**

- `README.md` — append a short "Sample data (local development only)" subsection under "Local development".

No other files change.

---

## Task 1: Create the `dev` package marker

**Files:**
- Create: `apps/api/src/vibing_api/dev/__init__.py`

- [ ] **Step 1: Create the package marker file**

Create `apps/api/src/vibing_api/dev/__init__.py` with no content:

```python
```

(An empty file. The package needs to exist before `sample_data.py` can be imported as `vibing_api.dev.sample_data`.)

- [ ] **Step 2: Confirm Python sees the new package**

Run from the repo root:

```bash
cd apps/api && uv run python -c "import vibing_api.dev; print('ok')"
```

Expected: `ok` (no `ModuleNotFoundError`).

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/vibing_api/dev/__init__.py
git commit -m "VIB-13 Add empty dev package marker"
```

---

## Task 2: Define the curated dataset constants

**Files:**
- Create: `apps/api/src/vibing_api/dev/sample_data.py`

This task only adds the constants and a small `_iter_dataset_tables()` helper used by later tasks. No CLI, no DB writes yet.

- [ ] **Step 1: Create `sample_data.py` with the dataset constants**

Create `apps/api/src/vibing_api/dev/sample_data.py` with the following content:

```python
"""Local-development sample data for product UI validation.

Inserts a curated, deterministic set of workspaces, agent sessions,
approval requests, and inbox events. Every sample row has an id
prefixed with `sample-` and every sample workspace name starts with
`[sample] ` so rows are visible in the UI and removable in a single
DELETE per table. Not part of the production import graph.
"""

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
```

- [ ] **Step 2: Verify the module imports and the constants are well-formed**

Run from the repo root:

```bash
cd apps/api && uv run python -c "
from vibing_api.dev.sample_data import _DATASET, SAMPLE_ID_PREFIX
total = sum(len(rows) for _, rows in _DATASET)
ids = [row['id'] for _, rows in _DATASET for row in rows]
assert total == 12, total
assert all(i.startswith(SAMPLE_ID_PREFIX) for i in ids), ids
print('ok', total, 'rows')
"
```

Expected: `ok 12 rows`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/vibing_api/dev/sample_data.py
git commit -m "VIB-13 Define curated sample dataset constants"
```

---

## Task 3: Implement `seed(conn)` with a failing test

**Files:**
- Modify: `apps/api/src/vibing_api/dev/sample_data.py`
- Create: `apps/api/tests/test_sample_data.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_sample_data.py` with this content:

```python
from pathlib import Path

import pytest

from vibing_api.core.database import get_connection, init_db
from vibing_api.dev.sample_data import (
    SAMPLE_AGENT_SESSIONS,
    SAMPLE_APPROVAL_REQUESTS,
    SAMPLE_ID_PREFIX,
    SAMPLE_INBOX_EVENTS,
    SAMPLE_WORKSPACES,
    seed,
)


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    init_db()
    with get_connection() as conn:
        seed(conn)
        conn.commit()
    return db_path


def test_seed_inserts_curated_dataset(seeded_db: Path) -> None:
    expected = {
        "workspaces": len(SAMPLE_WORKSPACES),
        "agent_sessions": len(SAMPLE_AGENT_SESSIONS),
        "approval_requests": len(SAMPLE_APPROVAL_REQUESTS),
        "inbox_events": len(SAMPLE_INBOX_EVENTS),
    }
    with get_connection() as conn:
        for table, count in expected.items():
            row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE id LIKE ?",
                (f"{SAMPLE_ID_PREFIX}%",),
            ).fetchone()
            assert row[0] == count, f"{table}: expected {count}, got {row[0]}"
```

(`db_path` is the existing fixture in `apps/api/tests/conftest.py` that points `Settings.database_url` at `tmp_path`.)

- [ ] **Step 2: Run the test to verify it fails**

Run from `apps/api`:

```bash
cd apps/api && uv run pytest tests/test_sample_data.py::test_seed_inserts_curated_dataset -v
```

Expected: FAIL with `ImportError` on `seed` (the function doesn't exist yet).

- [ ] **Step 3: Implement `seed(conn)`**

Append to `apps/api/src/vibing_api/dev/sample_data.py`:

```python
import sqlite3


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
```

Add `import sqlite3` near the top of the module (next to the existing imports — currently the file has none, so add it as the first line after the module docstring).

- [ ] **Step 4: Run the test to verify it passes**

Run from `apps/api`:

```bash
cd apps/api && uv run pytest tests/test_sample_data.py::test_seed_inserts_curated_dataset -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/vibing_api/dev/sample_data.py apps/api/tests/test_sample_data.py
git commit -m "VIB-13 Implement seed/reset helpers"
```

---

## Task 4: Verify `seed` is idempotent

**Files:**
- Modify: `apps/api/tests/test_sample_data.py`

- [ ] **Step 1: Append the idempotency test**

Add to `apps/api/tests/test_sample_data.py`:

```python
def test_seed_is_idempotent(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        seed(conn)
        conn.commit()
    with get_connection() as conn:
        seed(conn)
        conn.commit()
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM workspaces WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()[0]
    assert total == len(SAMPLE_WORKSPACES)
```

- [ ] **Step 2: Run the test and verify it passes**

Run from `apps/api`:

```bash
cd apps/api && uv run pytest tests/test_sample_data.py::test_seed_is_idempotent -v
```

Expected: PASS (because `seed` calls `reset` first).

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_sample_data.py
git commit -m "VIB-13 Test seed idempotency"
```

---

## Task 5: Verify `reset` only touches sample rows

**Files:**
- Modify: `apps/api/tests/test_sample_data.py`
- Modify: `apps/api/src/vibing_api/dev/sample_data.py` (import only — `reset` already exists)

- [ ] **Step 1: Append the test that proves real rows survive `reset`**

Add to `apps/api/tests/test_sample_data.py`:

```python
from vibing_api.dev.sample_data import reset


def test_reset_removes_only_sample_rows(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO workspaces "
            "(id, name, source_type, source_value, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "real-1",
                "real workspace",
                "local_folder",
                "/tmp/real",
                "created",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        seed(conn)
        conn.commit()
    with get_connection() as conn:
        removed = reset(conn)
        conn.commit()
    assert removed == 12
    with get_connection() as conn:
        remaining_sample = conn.execute(
            "SELECT COUNT(*) FROM workspaces WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()[0]
        real_row = conn.execute(
            "SELECT id, name FROM workspaces WHERE id = ?",
            ("real-1",),
        ).fetchone()
    assert remaining_sample == 0
    assert real_row is not None
    assert real_row[0] == "real-1"
```

Merge the new `reset` import into the existing `from vibing_api.dev.sample_data import …` block at the top of the test file rather than adding a second import line.

- [ ] **Step 2: Run the test**

```bash
cd apps/api && uv run pytest tests/test_sample_data.py::test_reset_removes_only_sample_rows -v
```

Expected: PASS.

- [ ] **Step 3: Add a second test: reset on an empty DB is safe**

Append to `apps/api/tests/test_sample_data.py`:

```python
def test_reset_on_empty_db_is_safe(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        removed = reset(conn)
        conn.commit()
    assert removed == 0
```

- [ ] **Step 4: Run both tests**

```bash
cd apps/api && uv run pytest tests/test_sample_data.py -v -k reset
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_sample_data.py
git commit -m "VIB-13 Test reset preserves real rows and handles empty DB"
```

---

## Task 6: Implement `status(conn)` with a test

**Files:**
- Modify: `apps/api/src/vibing_api/dev/sample_data.py`
- Modify: `apps/api/tests/test_sample_data.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_sample_data.py`:

```python
from vibing_api.dev.sample_data import status


def test_status_counts_sample_rows(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        before = status(conn)
        seed(conn)
        conn.commit()
        after = status(conn)
        reset(conn)
        conn.commit()
        after_reset = status(conn)
    assert before == {
        "workspaces": 0,
        "agent_sessions": 0,
        "approval_requests": 0,
        "inbox_events": 0,
    }
    assert after == {
        "workspaces": len(SAMPLE_WORKSPACES),
        "agent_sessions": len(SAMPLE_AGENT_SESSIONS),
        "approval_requests": len(SAMPLE_APPROVAL_REQUESTS),
        "inbox_events": len(SAMPLE_INBOX_EVENTS),
    }
    assert after_reset == before
```

Merge `status` into the existing `from vibing_api.dev.sample_data import …` block at the top of the test file.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && uv run pytest tests/test_sample_data.py::test_status_counts_sample_rows -v
```

Expected: FAIL with `ImportError` on `status`.

- [ ] **Step 3: Implement `status(conn)`**

Append to `apps/api/src/vibing_api/dev/sample_data.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/api && uv run pytest tests/test_sample_data.py::test_status_counts_sample_rows -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/vibing_api/dev/sample_data.py apps/api/tests/test_sample_data.py
git commit -m "VIB-13 Add status helper for sample row counts"
```

---

## Task 7: Add the HTTP smoke test

This is the one end-to-end check that proves seeded workspaces show up in the existing API surface — the "UI validation" path the ticket cares about.

**Files:**
- Modify: `apps/api/tests/test_sample_data.py`

- [ ] **Step 1: Add the test using the existing `client` fixture**

Append to `apps/api/tests/test_sample_data.py`:

```python
from fastapi.testclient import TestClient


def test_seeded_sample_workspaces_visible_via_api(client: TestClient) -> None:
    with get_connection() as conn:
        seed(conn)
        conn.commit()
    response = client.get("/api/v1/workspaces")
    assert response.status_code == 200
    names = sorted(item["name"] for item in response.json()["items"])
    assert names == [
        "[sample] vibing-api",
        "[sample] vibing-cli",
        "[sample] vibing-web",
    ]
```

The `client` fixture in `conftest.py` already depends on `db_path` and instantiates the app with `init_db()` via its `lifespan`, so the schema is in place when `seed(conn)` runs.

- [ ] **Step 2: Run the test**

```bash
cd apps/api && uv run pytest tests/test_sample_data.py::test_seeded_sample_workspaces_visible_via_api -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_sample_data.py
git commit -m "VIB-13 Smoke test seeded workspaces via HTTP"
```

---

## Task 8: Implement the argparse CLI

**Files:**
- Modify: `apps/api/src/vibing_api/dev/sample_data.py`

This task wires `main(argv)` and the `__main__` block. It is exercised by the next task's tests.

- [ ] **Step 1: Add `main()` and the entrypoint**

Append to `apps/api/src/vibing_api/dev/sample_data.py`:

```python
import argparse
import sys

from vibing_api.core.database import get_connection, init_db


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
```

The new imports (`argparse`, `sys`, and the two database functions) can be added next to the existing `import sqlite3` at the top of the module — group the stdlib imports together and the `vibing_api.core.database` import below them.

- [ ] **Step 2: Sanity-check the CLI from a fresh tmp DB**

Run from `apps/api`:

```bash
cd apps/api && VIBING_DATABASE_URL=sqlite:///$(mktemp -u --suffix=.db) uv run python -m vibing_api.dev.sample_data seed
```

Expected: prints exactly `seeded 12 rows across 4 tables.` and exits 0.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/vibing_api/dev/sample_data.py
git commit -m "VIB-13 Add argparse CLI for sample_data module"
```

---

## Task 9: Test the CLI end-to-end

**Files:**
- Modify: `apps/api/tests/test_sample_data.py`

- [ ] **Step 1: Append a CLI dispatch test using `capsys`**

Append to `apps/api/tests/test_sample_data.py`:

```python
from vibing_api.dev.sample_data import main


def test_main_dispatches_subcommands(
    db_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["seed"]) == 0
    seed_out = capsys.readouterr().out.strip()
    assert seed_out == "seeded 12 rows across 4 tables."

    assert main(["status"]) == 0
    status_out = capsys.readouterr().out.strip().splitlines()
    assert status_out == [
        f"workspaces: {len(SAMPLE_WORKSPACES)}",
        f"agent_sessions: {len(SAMPLE_AGENT_SESSIONS)}",
        f"approval_requests: {len(SAMPLE_APPROVAL_REQUESTS)}",
        f"inbox_events: {len(SAMPLE_INBOX_EVENTS)}",
    ]

    assert main(["reset"]) == 0
    reset_out = capsys.readouterr().out.strip()
    assert reset_out == "removed 12 sample rows."

    assert main(["reset"]) == 0
    reset_again_out = capsys.readouterr().out.strip()
    assert reset_again_out == "removed 0 sample rows."
```

Merge `main` into the existing `from vibing_api.dev.sample_data import …` block at the top of the test file.

- [ ] **Step 2: Run the test**

```bash
cd apps/api && uv run pytest tests/test_sample_data.py::test_main_dispatches_subcommands -v
```

Expected: PASS.

- [ ] **Step 3: Run the full new test file to confirm everything still passes**

```bash
cd apps/api && uv run pytest tests/test_sample_data.py -v
```

Expected: all 7 tests PASS:

- `test_seed_inserts_curated_dataset`
- `test_seed_is_idempotent`
- `test_reset_removes_only_sample_rows`
- `test_reset_on_empty_db_is_safe`
- `test_status_counts_sample_rows`
- `test_seeded_sample_workspaces_visible_via_api`
- `test_main_dispatches_subcommands`

- [ ] **Step 4: Run the whole API test suite to confirm no regressions**

```bash
cd apps/api && uv run pytest -q
```

Expected: all tests PASS (existing tests plus the 7 new ones).

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_sample_data.py
git commit -m "VIB-13 Test sample_data CLI dispatch"
```

---

## Task 10: Lint and type-check

**Files:** none (verification only).

- [ ] **Step 1: Run ruff against the new file and the test file**

```bash
cd apps/api && uv run ruff check src/vibing_api/dev/sample_data.py tests/test_sample_data.py
```

Expected: `All checks passed!` If ruff reports issues, fix them in place and re-run.

- [ ] **Step 2: Run mypy against the new module**

```bash
cd apps/api && uv run mypy src/vibing_api/dev/sample_data.py
```

Expected: `Success: no issues found in 1 source file`. If mypy reports issues, fix them in place and re-run.

- [ ] **Step 3: Commit any fix-ups (skip if there was nothing to fix)**

```bash
git add apps/api/src/vibing_api/dev/sample_data.py apps/api/tests/test_sample_data.py
git commit -m "VIB-13 Fix lint/type issues in sample_data"
```

---

## Task 11: Document the command in the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append the sample-data subsection under "Local development"**

Open `README.md` and locate the "Production-like preview (single container)" subsection under `## Local development`. Insert a new subsection **before** "Production-like preview":

```markdown
### Sample data (local development only)

Populate the dashboard, inbox, and approval queue with curated sample rows for UI validation:

```bash
cd apps/api
uv run python -m vibing_api.dev.sample_data seed     # idempotent
uv run python -m vibing_api.dev.sample_data status   # show counts
uv run python -m vibing_api.dev.sample_data reset    # remove samples
```

Every sample row's `id` is prefixed with `sample-` and every sample workspace name starts with `[sample]`. Real rows created via the API are never touched by `reset`.
```

(The triple-backtick `bash` block sits inside the surrounding markdown; the README's own triple-backtick fences elsewhere show the same nesting.)

- [ ] **Step 2: Sanity-check the README renders without broken fences**

Run from the repo root:

```bash
grep -c '^```' README.md
```

Expected: an even number (every opening fence has a closing fence).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "VIB-13 Document sample data command in README"
```

---

## Task 12: Final verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite one last time**

```bash
cd apps/api && uv run pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Exercise the CLI end-to-end against a real DB file**

Create a throwaway DB, seed, check, status, reset, status:

```bash
cd apps/api
TMP_DB=$(mktemp -u --suffix=.db)
export VIBING_DATABASE_URL=sqlite:///${TMP_DB}
uv run python -m vibing_api.dev.sample_data status
uv run python -m vibing_api.dev.sample_data seed
uv run python -m vibing_api.dev.sample_data status
uv run python -m vibing_api.dev.sample_data reset
uv run python -m vibing_api.dev.sample_data status
unset VIBING_DATABASE_URL
rm -f "${TMP_DB}"
```

Expected output (line by line):

```
workspaces: 0
agent_sessions: 0
approval_requests: 0
inbox_events: 0
seeded 12 rows across 4 tables.
workspaces: 3
agent_sessions: 3
approval_requests: 2
inbox_events: 4
removed 12 sample rows.
workspaces: 0
agent_sessions: 0
approval_requests: 0
inbox_events: 0
```

- [ ] **Step 3: Confirm `git status` is clean**

```bash
git status
```

Expected: `nothing to commit, working tree clean`.

- [ ] **Step 4: Confirm the commit log shows the VIB-13 series**

```bash
git log --oneline -n 12
```

Expected: the most recent commits are all prefixed `VIB-13` (one per task that produced a commit). The plan and spec commits from earlier are below them in the log.
