# VIB-13 — Sample data for local product testing

## Context

Vibing is a local operations center for AI coding agents: a React + Vite + TypeScript frontend backed by a FastAPI + SQLite service (`apps/api`). VIB-8/9/10 shipped the shell, workspace list, and settings page; VIB-11/12 added local diagnostics and the developer setup docs. The runtime that would actually create workspaces, sessions, inbox events, and approvals is not yet wired up, so the dashboard, inbox, and approval queue have no way to render anything besides empty states.

VIB-13 unblocks UI work on those screens by adding a local-only command that seeds the SQLite database with a curated set of sample rows, and a command to remove them again. Sample rows are clearly tagged so they cannot be confused with real data.

## Goal

Stand up a single dev-only Python module that can `seed`, `reset`, and `status` a deterministic sample dataset covering workspaces, agent sessions, inbox events, and approval requests — sized strictly to the ticket's acceptance criteria.

## Acceptance criteria (from VIB-13)

- A local development command can create sample workspaces.
- Sample session statuses can be created for UI validation.
- Sample inbox events can be created for UI validation.
- Sample approval items can be created for UI validation.
- Sample data can be removed or reset safely.
- Sample data is clearly marked as local development only.

### How each criterion is met

| Criterion | Treatment this ticket |
|---|---|
| Local dev command creates sample workspaces | `python -m vibing_api.dev.sample_data seed` inserts 3 sample workspaces |
| Sample session statuses | Same command inserts 3 agent sessions covering `running`, `waiting_for_approval`, `completed` |
| Sample inbox events | Same command inserts 4 inbox events, one per domain `event_type` the UI surfaces (`question`, `approval_request`, `failure`, `completion`) |
| Sample approval items | Same command inserts 2 approval requests (`pending`, `approved`) |
| Removed/reset safely | `... reset` deletes only rows with `id LIKE 'sample-%'`. Real rows are untouched. `seed` is idempotent (it calls `reset` first) |
| Clearly marked as local-dev only | Every sample row's `id` starts with `sample-`; every sample workspace `name` starts with `[sample]`. Visible without any UI changes |

## Approach

Add a new `apps/api/src/vibing_api/dev/` package containing one feature file: `sample_data.py`. It exposes pure helper functions (`seed`, `reset`, `status`) that take a `sqlite3.Connection`, plus an argparse-driven `main()` for command-line use. The dataset is a set of module-level constants — deterministic, fixed timestamps, no randomness — so re-seeding is byte-identical across runs.

The command is invoked as:

```bash
uv run python -m vibing_api.dev.sample_data seed
uv run python -m vibing_api.dev.sample_data reset
uv run python -m vibing_api.dev.sample_data status
```

This avoids adding a new console script entry in `pyproject.toml`, matches how `uvicorn` is already launched, and keeps dev tooling out of the production HTTP surface.

## File layout

```
apps/api/src/vibing_api/dev/
  __init__.py              # empty; makes `dev` a package
  sample_data.py           # constants, helpers, argparse main
apps/api/tests/
  test_sample_data.py      # new
```

No changes to existing modules.

## Sample marker convention

- Every inserted row has an `id` that starts with `sample-`. Examples: `sample-ws-web`, `sample-as-api`, `sample-ar-001`, `sample-ie-001`.
- Every sample workspace `name` starts with `[sample] ` so the workspace list visually distinguishes them without any frontend code change.
- `reset` deletes by `id LIKE 'sample-%'` on each of the four tables. No other heuristic is used.
- Reset order is the reverse of insert order so foreign-key cascades never need to fire mid-statement.

## Dataset (curated, fixed)

All `created_at` / `updated_at` / `decided_at` fields use the fixed ISO string `2026-01-01T12:00:00+00:00` so the inserted rows are byte-identical across runs.

### Workspaces (3 rows)

| `id` | `name` | `source_type` | `source_value` | `status` |
|---|---|---|---|---|
| `sample-ws-web` | `[sample] vibing-web` | `local_folder` | `/sample/projects/vibing-web` | `running` |
| `sample-ws-api` | `[sample] vibing-api` | `local_folder` | `/sample/projects/vibing-api` | `stopped` |
| `sample-ws-cli` | `[sample] vibing-cli` | `local_folder` | `/sample/projects/vibing-cli` | `error` |

Status mix exercises the three colour buckets in the workspace-list status badge (`running` → green, `stopped` → muted, `error` → red).

### Agent sessions (3 rows)

| `id` | `workspace_id` | `status` |
|---|---|---|
| `sample-as-web` | `sample-ws-web` | `running` |
| `sample-as-api` | `sample-ws-api` | `waiting_for_approval` |
| `sample-as-cli` | `sample-ws-cli` | `completed` |

`started_at` is set to the fixed timestamp for all three; `ended_at` is set only for the `completed` row; `last_event_at` is set to the fixed timestamp for all three.

### Approval requests (2 rows)

| `id` | `workspace_id` | `agent_session_id` | `status` | `requested_action` | `decided_at` |
|---|---|---|---|---|---|
| `sample-ar-001` | `sample-ws-api` | `sample-as-api` | `pending` | `run: pnpm migrate` | `NULL` |
| `sample-ar-002` | `sample-ws-web` | `sample-as-web` | `approved` | `run: rm node_modules` | fixed ts |

### Inbox events (4 rows)

| `id` | `workspace_id` | `agent_session_id` | `approval_request_id` | `event_type` | `status` |
|---|---|---|---|---|---|
| `sample-ie-001` | `sample-ws-api` | `sample-as-api` | `NULL` | `question` | `unread` |
| `sample-ie-002` | `sample-ws-api` | `sample-as-api` | `sample-ar-001` | `approval_request` | `unread` |
| `sample-ie-003` | `sample-ws-cli` | `sample-as-cli` | `NULL` | `failure` | `read` |
| `sample-ie-004` | `sample-ws-cli` | `sample-as-cli` | `NULL` | `completion` | `resolved` |

One row per event type used by the inbox, with status spread across `unread` / `read` / `resolved` so the inbox UI isn't visually uniform. `runtime_events` and `session_summaries` are intentionally not seeded (see Out of scope).

## CLI behaviour

`main(argv: list[str] | None = None) -> int` uses `argparse` with three subcommands and no other flags:

- `seed` — opens a connection via `database.get_connection()`, calls `init_db()` first to make sure the schema is present on a fresh checkout, then calls `reset(conn)` and `seed(conn)`, commits once, and prints `seeded N rows across 4 tables.` where N is the sum of the four dataset sizes.
- `reset` — opens a connection, calls `reset(conn)`, commits, and prints `removed N sample rows.` (including `removed 0 sample rows.` when nothing is seeded — no error).
- `status` — opens a connection, runs `SELECT COUNT(*) FROM <table> WHERE id LIKE 'sample-%'` for each of the four tables, and prints one line per table, e.g.:
  ```
  workspaces: 3
  agent_sessions: 3
  approval_requests: 2
  inbox_events: 4
  ```

All three subcommands honour `VIBING_DATABASE_URL` because they reuse `database.get_connection()`. The script exits `0` on success.

## Module shape

```python
# apps/api/src/vibing_api/dev/sample_data.py
import argparse
import sqlite3
import sys

from vibing_api.core.database import get_connection, init_db

SAMPLE_ID_PREFIX = "sample-"
SAMPLE_NAME_PREFIX = "[sample] "
FIXED_TS = "2026-01-01T12:00:00+00:00"

SAMPLE_WORKSPACES: tuple[dict, ...] = (...)
SAMPLE_AGENT_SESSIONS: tuple[dict, ...] = (...)
SAMPLE_APPROVAL_REQUESTS: tuple[dict, ...] = (...)
SAMPLE_INBOX_EVENTS: tuple[dict, ...] = (...)

_SAMPLE_TABLES: tuple[str, ...] = (
    "inbox_events",
    "approval_requests",
    "agent_sessions",
    "workspaces",
)  # reset order = reverse of insert order

def seed(conn: sqlite3.Connection) -> int: ...
def reset(conn: sqlite3.Connection) -> int: ...
def status(conn: sqlite3.Connection) -> dict[str, int]: ...

def main(argv: list[str] | None = None) -> int: ...

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

The dataset constants stay in this file (not a separate `fixtures.py`) so the whole feature fits in one place. They are module-level so tests can import and assert against them directly.

## Tests

`apps/api/tests/test_sample_data.py` (new). Reuses the existing `db_path` fixture from `conftest.py`; the new tests open their own connections via `get_connection()` rather than going through `TestClient`, except for one HTTP smoke check.

- `test_seed_inserts_curated_dataset` — call `init_db()` then `seed(conn)`; assert per-table row counts match the dataset sizes (3 / 3 / 2 / 4) and that every inserted `id` starts with `sample-`.
- `test_seed_is_idempotent` — call `seed(conn)` twice; counts match the curated dataset both times; no `UNIQUE` constraint violations.
- `test_reset_removes_only_sample_rows` — insert one real workspace via raw SQL (`id="real-1"`), call `seed(conn)` then `reset(conn)`; the real workspace is still present and no `sample-` rows remain in any of the four tables.
- `test_reset_on_empty_db_is_safe` — call `reset(conn)` against a fresh schema; no error, returns 0.
- `test_status_counts_sample_rows` — after `seed`, `status(conn)` returns `{"workspaces": 3, "agent_sessions": 3, "approval_requests": 2, "inbox_events": 4}`. After `reset`, all values are `0`.
- `test_seeded_sample_workspaces_visible_via_api` — call `init_db()` and `seed(conn)`, then use the existing `client` fixture to `GET /api/v1/workspaces`; assert the three `[sample]` workspaces are in the response. This is the "UI validation" path the ticket cares about.

`main()` itself is exercised indirectly via the helper-function tests above. A separate `test_main_dispatches_subcommands` calls `main(["seed"])`, `main(["status"])`, `main(["reset"])` end-to-end and asserts each returns `0` and prints the expected line (captured via `capsys`).

## Documentation

Append a short subsection to `README.md` under "Local development":

```
### Sample data (local development only)

To populate the dashboard, inbox, and approval queue with curated sample
rows for UI validation:

    cd apps/api
    uv run python -m vibing_api.dev.sample_data seed     # idempotent
    uv run python -m vibing_api.dev.sample_data status   # show counts
    uv run python -m vibing_api.dev.sample_data reset    # remove samples

Every sample row's id is prefixed with `sample-` and every sample
workspace name starts with `[sample]`. Real rows are never touched by
`reset`.
```

## Out of scope

- Seeding `runtime_events` or `session_summaries`. Neither is rendered by any current UI; adding them now would be speculative work.
- A frontend "seed sample data" button. Command-line only.
- Faker, randomization, or per-run variation. The dataset is hand-written and stable so screenshots and tests stay deterministic.
- A `--count` or `--profile` flag. The single curated dataset is the only profile.
- A schema column to mark sample rows. The `sample-` id prefix carries that signal and avoids a migration for a dev-only feature.
- Updating the diagnostics endpoint, settings page, or runtime detection.

## Risks and watchouts

- **Order of inserts matters.** Foreign keys require workspaces → agent_sessions → approval_requests → inbox_events on insert; reset runs the reverse. The `_SAMPLE_TABLES` constant codifies the reset order so a future contributor can't accidentally re-order it.
- **`init_db()` must run before `seed`** on a fresh checkout, because the SQLite file may not exist yet. The CLI calls `init_db()` itself; tests rely on the `db_path` fixture pointing at a tmp file that the test calls `init_db()` against. Both paths are covered.
- **`approval_requests.agent_session_id` is `NOT NULL` and references `agent_sessions(id) ON DELETE CASCADE`.** A `reset` that deleted `agent_sessions` first would cascade-delete the approval rows. Reverse-order deletion (inbox_events → approval_requests → agent_sessions → workspaces) prevents this from being a problem in practice, but matters for correctness.
- **`inbox_events.approval_request_id` is `ON DELETE SET NULL`.** Acceptable: if a `reset` ever ran partially, leftover inbox rows would point to `NULL`, not a dangling id. Not a concern with the chosen reset order, but documented for clarity.
- **Naming collision** is avoided because real workspaces created via `POST /api/v1/workspaces` get UUID-v4 ids, which never start with `sample-`. The convention is self-enforcing for the real flow.
- **Re-seeding wipes any sample-prefixed row** the user may have manually inserted. This is intentional (the prefix means "owned by the seeder"), but worth calling out so a tester doesn't lose hand-edits.

## Done-when checklist

- `uv run pytest` passes, including the new `test_sample_data.py`.
- `uv run python -m vibing_api.dev.sample_data seed` (with a fresh DB) prints `seeded 12 rows across 4 tables.` and exits 0.
- `uv run python -m vibing_api.dev.sample_data status` prints the expected per-table counts.
- Running `seed` twice in a row leaves the DB with exactly the curated dataset (idempotent).
- A workspace created via `POST /api/v1/workspaces` is still present after `reset`.
- `GET /api/v1/workspaces` returns the three `[sample]` workspaces after `seed`.
- The README "Sample data (local development only)" subsection is in place.
