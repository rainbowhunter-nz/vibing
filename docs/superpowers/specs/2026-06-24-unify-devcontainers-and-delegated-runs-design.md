# Design: Unify devcontainers + move delegated-runs projection in-memory

Date: 2026-06-24
Status: approved (pending spec review)

Two independent cleanups that both remove "this state is special" complexity. They
share no code and can be implemented/merged separately, but are specced together
because they were requested together. **Ordering:** land Part B first (or together) —
Part A's `delegated_runs` 404 check assumes every devcontainer has a DB row, which is
only universally true once Part B persists discovered ones.

## Motivation

A runtime running in a *discovered* devcontainer could not persist its Delegated
Runs: `delegated_runs.devcontainer_id` had a FK to `devcontainers(id)`, but
discovered devcontainers are virtual and never persisted, so every insert failed
`FOREIGN KEY constraint failed`. The deeper issues:

1. **Delegated runs don't belong in SQLite.** Per ADR-0016 they are non-durable,
   best-effort *observation* (full-snapshot replace, lost-and-rebuilt on runtime
   reconnect). That is exactly the semantics of the in-memory harness-status cache
   in `LiveStateStore` — yet runs went to the DB by pattern inertia, dragging in
   FK/migration/cascade friction.
2. **The discovered/manual split is unnecessary.** "Virtual, never persisted"
   exists only to avoid syncing the DB with the filesystem. The cost is that every
   consumer must not assume a devcontainer_id has a DB row (the FK was one such
   illegal assumption; `list_delegated_runs` still has the same latent 404 bug).
   Persisting discovered folders as ordinary rows, reconciled at startup, removes
   the split entirely.

## Part A — Delegated-runs projection → `LiveStateStore`, drop the table

### Data flow
```
runtime --WS delegated_runs snapshot--> runtime.py
  --> record_delegated_runs(live_state, id, items, broadcaster)
        live_state.set_delegated_runs(id, items)   # in-memory, replace
        broadcaster.publish(delegated_runs, [id])  # SSE invalidation
frontend --GET /devcontainers/{id}/delegated-runs--> live_state.get_delegated_runs(id)
```

### Changes
- **`core/live_state.py`**: add `_delegated_runs: dict[str, list[DelegatedRunItem]]`
  with `set_delegated_runs` / `get_delegated_runs` / `evict_delegated_runs`,
  mirroring the `_harness` map. Documented as never-persisted, rebuilt on runtime
  reconnect (verified: the runtime's `_on_registered` re-pushes a full snapshot on
  every (re)connect, so a CP restart self-heals).
- **Eviction lifetime**: delegated runs are container-scoped like harness status —
  evict in `_teardown_container` right beside `evict_harness` (container stop /
  remove-container / DELETE all flow through it). **Not** evicted on a plain runtime
  WS disconnect — a crash-and-reconnect would flicker, and the reconnect re-pushes
  the truth anyway.
- **`core/runtime_intake.py`**: `persist_delegated_runs` → `record_delegated_runs(
  live_state, devcontainer_id, items, broadcaster)` — writes the map and publishes
  the SSE. No DB access.
- **`api/routes/runtime.py`**: call `record_delegated_runs` with
  `websocket.app.state.live_state`.
- **`api/routes/delegated_runs.py`**: serve from `live_state.get_delegated_runs(id)`
  (`None` → `[]`), mapping `DelegatedRunItem` → `DelegatedRunList`. Removes the empty
  stub so the endpoint returns real activity. 404 check uses
  `DevcontainerRepository.get` (a real row exists for every devcontainer after Part B).
- **Drop**: `repositories/delegated_runs.py`; the `delegated_runs` table; the
  delete-route delegated-runs cleanup; the schema FK-rebuild migration (replaced by
  `DROP TABLE IF EXISTS delegated_runs`).

### Schema
`SCHEMA_VERSION` stays `"9"` (the v9 bump is still unreleased in this branch).
v9 now means: no `delegated_runs` table. `_drop_legacy` runs
`DROP TABLE IF EXISTS delegated_runs` (idempotent for fresh and existing DBs).

### Tests
- `LiveStateStore`: set/get/evict delegated runs.
- `runtime_intake`: `record_delegated_runs` writes the map + publishes SSE (no DB).
- `delegated_runs` API: returns recorded runs; `[]` when none; 404 unknown id.
- Remove: `test_delegated_runs_repository.py`, the delegated-runs DB tests in
  `test_database.py`, and the delete-cleanup test.

## Part B — Unify devcontainers (drop discovered/virtual)

### Model
The filesystem is the source of truth for *existence*; the DB is the steady-state
read model. A startup sync reconciles them. After boot, all reads hit the DB; there
is one kind of devcontainer.

### Startup sync — `core/devcontainer_sync.py`
Run in `lifespan` after `init_db()`:
1. `for folder in scan(devcontainers_dir): repo.upsert(folder.name, folder.path)`
2. `for row in repo.list(): if not is_devcontainer_folder(row.local_path):
   repo.delete(row.id); live_state.evict_*(row.id)` (harness, transient,
   runtime-transient, delegated runs).

Stale = local_path no longer contains a `.devcontainer/` folder, applied uniformly
to every row (manual-origin included). New folders added at runtime appear after
restart or via POST — accepted tradeoff. **Orphan tradeoff:** if the folder is gone
but its container is still running, eviction removes the only row referencing it,
leaving an invisible orphan container (killable via `docker rm -f`). Accepted as a
genuine edge — sync stays Docker-free and fast; documented in the ADR consequences.

### Schema
- `devcontainers` gains `UNIQUE(local_path)`.
- Migration: rebuild `devcontainers` to add the constraint if absent (table-rebuild
  pattern; foreign-key-free table, so a straight copy). **Dedup first** — POST has no
  duplicate-path guard today, so existing DBs may hold duplicate paths; before adding
  the constraint, keep one row per `local_path` (the **oldest `created_at`**, to
  preserve the original id/bookmarks) and delete the rest. Makes the migration total.

### Repository — `repositories/devcontainers.py`
- `upsert(name, local_path) -> DevcontainerRecord`:
  `INSERT (id, …) VALUES (uuid5(NAMESPACE, local_path), …)
   ON CONFLICT(local_path) DO NOTHING`, then re-`get` by path. Idempotent; id stable
  per path. **`DO NOTHING` (not `DO UPDATE`)** — `name` is set once at first insert and
  is user-owned thereafter; neither startup sync nor a re-POST may overwrite it.
- POST `create` route uses `upsert` — re-adding a known path returns the existing row
  unchanged (a different name in the re-POST is silently ignored). POST still returns
  `201` always; we do not special-case insert-vs-conflict (corner case; UI prevents
  duplicate adds).
- `get`/`list`/`delete`/`update` unchanged (`update` remains the user rename path).

### Discovery — `core/discovery.py`
- Keep `scan`; extract `is_devcontainer_folder(path: Path) -> bool` (the
  `child.is_dir() and (child/'.devcontainer').is_dir()` predicate) reused by both
  `scan` and the stale check.
- `discovered_id(path)` → shared `devcontainer_id(path)` = `uuid5(NAMESPACE, path)`,
  used by `upsert`.

### Routes — `api/routes/devcontainers.py`
- Delete `core/catalog.py` and `ResolvedDevcontainer`. Routes resolve via
  `DevcontainerRepository.get` directly; `app.state.catalog` removed, repo/connection
  wired as before catalog.
- Drop `source` / `DevcontainerSource` from schemas and responses.
- DELETE always removes the DB row (no manual/discovered branch). `remove-container`
  unchanged (kills container, keeps row).
- `app.state` no longer holds a `scanner`/catalog; `lifespan` calls the sync.

### Frontend (`apps/web`)
- `lib/api/types.ts`: remove `DevcontainerSource` and `source`.
- `routes/DevcontainerDetail.tsx`: remove `SourceBadge` and its usage.
- `mock/state/devcontainers.ts`: delete the `source === 'discovered'` delete
  special-casing (delete always removes); drop `source` from the view/seeds.
- Fix affected mock/component tests and seeds.

### Docs
- New `docs/adr/0020-*`: discovered devcontainers are persisted via startup sync,
  not virtual; the manual/discovered distinction and `source` field are removed.
  Add the index line in `docs/adr/CLAUDE.md`.
- Update `src/vibing_api/CLAUDE.md` (catalog/discovery/source/delegated-runs bullets,
  schema description) and `src/CLAUDE.md` if it mentions discovered/virtual.

### Tests
- `devcontainer_sync`: upserts new folders; evicts rows with a missing/invalid path
  and clears their live_state; idempotent across two runs.
- `DevcontainerRepository.upsert`: insert then conflict-update; stable id per path.
- API: POST same path twice is idempotent; DELETE removes the row; no `source` field.
- Remove catalog tests; update devcontainer API/lifecycle tests that asserted
  `source` or discovered-specific behavior.

## Out of scope
- Wiring the frontend to render the now-populated `delegated-runs` endpoint (the
  React consumption layer) — Part A makes the API correct; FE rendering is separate.
- A runtime rescan endpoint (POST covers known paths; restart covers new folders).

## Verification
`uv run ruff check src tests`, `uv run ruff format --check src tests`,
`uv run mypy src`, `uv run pytest -q`; frontend `pnpm test`. Manual: start with a
discovered folder, confirm it persists as a row, delegated runs from its runtime
appear at the API, and removing the folder evicts it on restart.
