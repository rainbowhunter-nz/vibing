# Unify Devcontainers + Delegated-Runs In-Memory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove two "this state is special" complexities — move the Delegated-Runs projection out of SQLite into `LiveStateStore`, and persist discovered devcontainers as ordinary rows reconciled at startup (no more manual/discovered split).

**Architecture:** Part A makes Delegated Runs a container-scoped in-memory cache mirroring the existing harness-status cache (runtime re-pushes a full snapshot on every reconnect, so a CP restart self-heals). Part B makes the filesystem the source of truth for *existence* and the DB the steady-state read model, reconciled by a startup sync; the catalog/merge layer and `source` field are deleted.

**Tech Stack:** Python 3.13, FastAPI, SQLite (`sqlite3`), pydantic, pytest, ruff, mypy; frontend React + Vitest + MSW.

## Global Constraints

- Python checks (repo root): `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`. All must pass per task.
- Frontend checks (`apps/web`): `pnpm test`.
- `SCHEMA_VERSION` ends this work at `"9"` (unreleased bump within this branch).
- Devcontainer ids for filesystem folders: `uuid5(NAMESPACE, local_path)` where `NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")` (existing constant in `discovery.py`).
- `name` is set once on first insert and user-owned thereafter — startup sync and re-POST must never overwrite it.
- TDD: write the failing test first, watch it fail, implement, watch it pass, commit. Frequent commits.
- **Ordering:** complete Part B before merging Part A's route change, since Part A's 404 check assumes every devcontainer has a DB row.

## Baseline precondition

Before Task A1, the working tree must be clean (all current edits committed) so per-task commits stay focused. The earlier FK hotfix (schema rebuild migration, `DelegatedRunRepository.delete`, delete-route cleanup, and its tests) is **superseded** by Part A and will be removed by Tasks A2/A4.

---

# Part A — Delegated Runs → LiveStateStore

### Task A1: LiveStateStore delegated-runs cache

**Files:**
- Modify: `src/vibing_api/core/live_state.py`
- Test: `tests/api/test_live_state.py` (create if absent)

**Interfaces:**
- Produces:
  - `LiveStateStore.set_delegated_runs(devcontainer_id: str, items: list[DelegatedRunItem]) -> None`
  - `LiveStateStore.get_delegated_runs(devcontainer_id: str) -> list[DelegatedRunItem] | None`
  - `LiveStateStore.evict_delegated_runs(devcontainer_id: str) -> None`
  - `DelegatedRunItem` is `vibing_protocol.DelegatedRunItem`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_live_state.py
from vibing_api.core.live_state import LiveStateStore
from vibing_protocol import DelegatedRunItem


def _item(run_id: str) -> DelegatedRunItem:
    return DelegatedRunItem(
        run_id=run_id, harness="codex", model="m", status="running",
        started_at="2026-06-20T00:00:00+00:00",
    )


def test_delegated_runs_set_get_evict() -> None:
    store = LiveStateStore()
    assert store.get_delegated_runs("dc1") is None
    store.set_delegated_runs("dc1", [_item("run-1")])
    assert [r.run_id for r in store.get_delegated_runs("dc1")] == ["run-1"]
    store.set_delegated_runs("dc1", [_item("run-2")])  # replace, not append
    assert [r.run_id for r in store.get_delegated_runs("dc1")] == ["run-2"]
    store.evict_delegated_runs("dc1")
    assert store.get_delegated_runs("dc1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_live_state.py -q`
Expected: FAIL (`AttributeError: 'LiveStateStore' object has no attribute 'set_delegated_runs'`).

- [ ] **Step 3: Implement**

In `live_state.py`: add the import `from vibing_protocol import DelegatedRunItem`, add `self._delegated_runs: dict[str, list[DelegatedRunItem]] = {}` in `__init__`, and the three methods mirroring the `_harness` map. Extend the module docstring's map list to include "delegated-runs snapshot cache (container-scoped; rebuilt on runtime reconnect)."

```python
    def set_delegated_runs(self, devcontainer_id: str, items: list[DelegatedRunItem]) -> None:
        self._delegated_runs[devcontainer_id] = items

    def evict_delegated_runs(self, devcontainer_id: str) -> None:
        self._delegated_runs.pop(devcontainer_id, None)

    def get_delegated_runs(self, devcontainer_id: str) -> list[DelegatedRunItem] | None:
        return self._delegated_runs.get(devcontainer_id)
```

- [ ] **Step 4: Run tests + checks**

Run: `uv run pytest tests/api/test_live_state.py -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/live_state.py tests/api/test_live_state.py
git commit -m "feat(live-state): add container-scoped delegated-runs cache"
```

---

### Task A2: record_delegated_runs (in-memory) + runtime WS wiring

**Files:**
- Modify: `src/vibing_api/core/runtime_intake.py`
- Modify: `src/vibing_api/api/routes/runtime.py:64-71`
- Test: `tests/api/test_runtime_intake.py` (create), update `tests/api/test_agent_channel.py` if it asserts DB persistence.

**Interfaces:**
- Consumes: `LiveStateStore.set_delegated_runs` (Task A1).
- Produces: `record_delegated_runs(live_state: LiveStateStore, devcontainer_id: str, items: list[DelegatedRunItem], broadcaster: Broadcaster | None = None) -> None` — sets the cache and publishes `SseEvent(scope="delegated_runs", ids=[devcontainer_id])`. No DB access.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_runtime_intake.py
from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_intake import record_delegated_runs
from vibing_protocol import DelegatedRunItem


def test_record_writes_cache_and_publishes() -> None:
    store = LiveStateStore()
    published: list[SseEvent] = []

    class _B(Broadcaster):
        def publish(self, event: SseEvent) -> None:  # type: ignore[override]
            published.append(event)

    item = DelegatedRunItem(
        run_id="r1", harness="codex", model="m", status="running",
        started_at="2026-06-20T00:00:00+00:00",
    )
    record_delegated_runs(store, "dc1", [item], _B())
    assert [r.run_id for r in store.get_delegated_runs("dc1")] == ["r1"]
    assert published == [SseEvent(scope="delegated_runs", ids=["dc1"])]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_runtime_intake.py -q`
Expected: FAIL (`ImportError: cannot import name 'record_delegated_runs'`).

- [ ] **Step 3: Implement**

Replace the body of `runtime_intake.py` (drop the DB/`persist_delegated_runs` version entirely):

```python
"""Inbound runtime reports → in-memory read model.

The Devcontainer Runtime pushes Delegated Run snapshots up the runtime channel.
Snapshots are kept in LiveStateStore (container-scoped, never persisted; rebuilt
when the runtime reconnects — ADR-0016) and publish an SSE invalidation.
"""

from vibing_protocol import DelegatedRunItem

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.live_state import LiveStateStore


def record_delegated_runs(
    live_state: LiveStateStore,
    devcontainer_id: str,
    items: list[DelegatedRunItem],
    broadcaster: Broadcaster | None = None,
) -> None:
    live_state.set_delegated_runs(devcontainer_id, items)
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="delegated_runs", ids=[devcontainer_id]))
```

In `runtime.py`, update the import (`from vibing_api.core.runtime_intake import record_delegated_runs`) and the `delegated_runs` branch:

```python
            if msg_type == "delegated_runs":
                try:
                    runs_env = DelegatedRunsEnvelope.model_validate(message)
                except ValidationError:
                    continue
                broadcaster = getattr(websocket.app.state, "broadcaster", None)
                try:
                    record_delegated_runs(
                        websocket.app.state.live_state,
                        runs_env.devcontainer_id,
                        runs_env.items,
                        broadcaster,
                    )
                except Exception:
                    logger.exception(
                        "Failed to record delegated runs (devcontainer=%s)",
                        runs_env.devcontainer_id,
                    )
                continue
```

- [ ] **Step 4: Run tests + checks**

Run: `uv run pytest tests/api/test_runtime_intake.py tests/api/test_agent_channel.py -q && uv run mypy src`
Expected: PASS. If `test_agent_channel.py` asserts the run landed in the DB, update it to assert via `app.state.live_state.get_delegated_runs(...)`.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/runtime_intake.py src/vibing_api/api/routes/runtime.py tests/api/test_runtime_intake.py tests/api/test_agent_channel.py
git commit -m "feat(runtime): record delegated runs in-memory, drop DB persistence"
```

---

### Task A3: delegated-runs GET serves from LiveStateStore

**Files:**
- Modify: `src/vibing_api/api/routes/delegated_runs.py`
- Test: `tests/api/test_delegated_runs_api.py`

**Interfaces:**
- Consumes: `LiveStateStore.get_delegated_runs` (A1); devcontainer resolution. Until Task B4 lands, resolution is `request.app.state.catalog.get(id)`; B4 swaps it to `app.state.devcontainer_store.get(id)`.
- Produces: `GET /devcontainers/{id}/delegated-runs` → real runs (`[]` when none), 404 for unknown id.

- [ ] **Step 1: Write the failing test** (append to `tests/api/test_delegated_runs_api.py`)

```python
def test_delegated_runs_returns_recorded_items(client):
    from vibing_protocol import DelegatedRunItem

    created = client.post(
        "/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"}
    ).json()
    client.app.state.live_state.set_delegated_runs(
        created["id"],
        [DelegatedRunItem(
            run_id="r1", harness="codex", model="m", status="running",
            started_at="2026-06-20T00:00:00+00:00",
        )],
    )
    resp = client.get(f"/api/v1/devcontainers/{created['id']}/delegated-runs")
    assert resp.status_code == 200
    assert [i["run_id"] for i in resp.json()["items"]] == ["r1"]
```

(`client.app` is the FastAPI app on the TestClient. If the project's `client` fixture exposes the app differently, use that handle — check `tests/api/conftest.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_delegated_runs_api.py::test_delegated_runs_returns_recorded_items -q`
Expected: FAIL (returns empty `items`).

- [ ] **Step 3: Implement**

Rewrite `delegated_runs.py`:

```python
from fastapi import APIRouter, Request

from vibing_api.api.schemas.delegated_runs import DelegatedRunItem, DelegatedRunList
from vibing_api.core.errors import DevcontainerNotFoundError

router = APIRouter(tags=["delegated-runs"], prefix="/devcontainers")


@router.get("/{devcontainer_id}/delegated-runs", response_model=DelegatedRunList)
def list_delegated_runs(devcontainer_id: str, request: Request) -> DelegatedRunList:
    if request.app.state.catalog.get(devcontainer_id) is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    items = request.app.state.live_state.get_delegated_runs(devcontainer_id) or []
    return DelegatedRunList(items=[DelegatedRunItem(**it.model_dump()) for it in items])
```

(The `it` items are `vibing_protocol.DelegatedRunItem`; `**it.model_dump()` maps onto the API schema's identical-field `DelegatedRunItem`.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_delegated_runs_api.py -q && uv run mypy src`
Expected: PASS (existing empty/404 tests still pass).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/api/routes/delegated_runs.py tests/api/test_delegated_runs_api.py
git commit -m "feat(api): serve delegated-runs from live-state cache"
```

---

### Task A4: Drop the delegated_runs table, repository, and superseded FK code

**Files:**
- Delete: `src/vibing_api/repositories/delegated_runs.py`, `tests/api/test_delegated_runs_repository.py`
- Modify: `src/vibing_api/core/schema.py`
- Modify: `tests/api/test_database.py`

**Interfaces:**
- Produces: schema v9 with no `delegated_runs` table; `_drop_legacy` drops it idempotently.

- [ ] **Step 1: Update schema tests first (failing)**

In `tests/api/test_database.py`: remove `test_delegated_runs_accepts_unpersisted_devcontainer` and `test_migrates_legacy_delegated_runs_fk` (both FK-era). Update the table-set test (around line 42) to no longer expect `delegated_runs`. Add:

```python
def test_delegated_runs_table_dropped(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert "delegated_runs" not in names
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_database.py::test_delegated_runs_table_dropped -q`
Expected: FAIL (table still created).

- [ ] **Step 3: Implement schema changes**

In `schema.py`: remove `_DELEGATED_RUNS_DDL` from `_TABLE_STATEMENTS`, delete the `_DELEGATED_RUNS_DDL` constant, delete `_drop_delegated_runs_fk` and its call in `apply_schema`, and remove the `delegated_runs` index from `_INDEX_STATEMENTS`. In `_drop_legacy` add:

```python
        conn.execute("DROP TABLE IF EXISTS delegated_runs")
```

Keep `SCHEMA_VERSION = "9"`.

- [ ] **Step 4: Delete the repository + its test**

```bash
git rm src/vibing_api/repositories/delegated_runs.py tests/api/test_delegated_runs_repository.py
```

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS. (Any remaining import of `DelegatedRunRepository` should already be gone after A2; if `grep -rn DelegatedRunRepository src` returns hits, remove them.)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(db): drop delegated_runs table and repository"
```

---

### Task A5: Evict delegated runs on container teardown

**Files:**
- Modify: `src/vibing_api/api/routes/devcontainers.py` (`_teardown_container`, ~line 128-132)
- Test: `tests/api/test_devcontainers_api.py`

**Interfaces:**
- Consumes: `LiveStateStore.evict_delegated_runs` (A1).

- [ ] **Step 1: Write the failing test** (append to `tests/api/test_devcontainers_api.py`)

```python
def test_remove_container_evicts_delegated_runs(client: TestClient, fake_cli) -> None:
    from vibing_protocol import DelegatedRunItem

    created = client.post(
        "/api/v1/devcontainers", json={"name": "rc", "local_path": "/tmp/rc2"}
    ).json()
    client.app.state.live_state.set_delegated_runs(
        created["id"],
        [DelegatedRunItem(
            run_id="r1", harness="codex", model="m", status="running",
            started_at="2026-06-20T00:00:00+00:00",
        )],
    )
    client.post(f"/api/v1/devcontainers/{created['id']}/remove-container")
    assert client.app.state.live_state.get_delegated_runs(created["id"]) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_devcontainers_api.py::test_remove_container_evicts_delegated_runs -q`
Expected: FAIL (runs still cached).

- [ ] **Step 3: Implement**

In `_teardown_container`, beside `live.evict_harness(resolved.id)` add:

```python
    live.evict_delegated_runs(resolved.id)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_devcontainers_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/api/routes/devcontainers.py tests/api/test_devcontainers_api.py
git commit -m "feat(api): evict delegated runs on container teardown"
```

---

# Part B — Unify devcontainers (drop discovered/virtual)

### Task B1: `is_devcontainer_folder` predicate + shared id

**Files:**
- Modify: `src/vibing_api/core/discovery.py`
- Test: `tests/api/test_discovery.py` (extend; create if absent)

**Interfaces:**
- Produces:
  - `is_devcontainer_folder(path: Path) -> bool` — true iff `path` is a dir containing a `.devcontainer/` dir.
  - `devcontainer_id(local_path: str) -> str` — `uuid5(NAMESPACE, local_path)` (rename of `discovered_id`; keep a module alias `discovered_id = devcontainer_id` only if other modules still import it — otherwise update callers).

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_discovery.py (add)
from pathlib import Path
from vibing_api.core.discovery import is_devcontainer_folder


def test_is_devcontainer_folder(tmp_path: Path) -> None:
    good = tmp_path / "proj"
    (good / ".devcontainer").mkdir(parents=True)
    assert is_devcontainer_folder(good)
    assert not is_devcontainer_folder(tmp_path / "missing")
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not is_devcontainer_folder(plain)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_discovery.py::test_is_devcontainer_folder -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**

In `discovery.py`:

```python
def is_devcontainer_folder(path: Path) -> bool:
    return path.is_dir() and (path / ".devcontainer").is_dir()


def devcontainer_id(local_path: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, local_path))
```

Refactor `scan` to use `is_devcontainer_folder(child)` and `devcontainer_id(path)`. Replace `discovered_id` usages project-wide (`grep -rn discovered_id src tests`) with `devcontainer_id`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_discovery.py -q && uv run mypy src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/discovery.py tests/api/test_discovery.py
git commit -m "refactor(discovery): extract is_devcontainer_folder + shared devcontainer_id"
```

---

### Task B2: `UNIQUE(local_path)` schema + dedup migration

**Files:**
- Modify: `src/vibing_api/core/schema.py`
- Test: `tests/api/test_database.py`

**Interfaces:**
- Produces: `devcontainers` has `UNIQUE(local_path)`; migration dedups existing duplicate paths (keep oldest `created_at`) before adding the constraint.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_database.py (add)
def test_devcontainers_local_path_unique(db_path: Path) -> None:
    init_db()
    ts = "2026-01-01T00:00:00Z"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO devcontainers (id, name, local_path, created_at, updated_at) "
            "VALUES ('a', 'a', '/tmp/x', ?, ?)", (ts, ts))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO devcontainers (id, name, local_path, created_at, updated_at) "
                "VALUES ('b', 'b', '/tmp/x', ?, ?)", (ts, ts))


def test_migration_dedups_duplicate_paths_keep_oldest(db_path: Path) -> None:
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE devcontainers (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "local_path TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute("INSERT INTO devcontainers VALUES "
                     "('old', 'old', '/tmp/dup', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
        conn.execute("INSERT INTO devcontainers VALUES "
                     "('new', 'new', '/tmp/dup', '2026-02-01T00:00:00Z', '2026-02-01T00:00:00Z')")
        conn.commit()
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM devcontainers WHERE local_path = '/tmp/dup'").fetchall()
    assert [r[0] for r in rows] == ["old"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/api/test_database.py -k "unique or dedups" -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `schema.py`: add `UNIQUE(local_path)` to the `devcontainers` CREATE statement. Add a migration run from `apply_schema` (after `_drop_legacy`, before indexes) that is idempotent:

```python
def _migrate_devcontainers_unique_path(conn: sqlite3.Connection) -> None:
    """Add UNIQUE(local_path); dedup existing rows (keep oldest created_at) first."""
    indexes = conn.execute("PRAGMA index_list(devcontainers)").fetchall()
    has_unique_path = any(
        row[2]  # unique flag
        and any(c[2] == "local_path"
                for c in conn.execute(f"PRAGMA index_info({row[1]})"))
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
```

Note: on a fresh DB the `CREATE TABLE` already carries `UNIQUE`, so `has_unique_path` is true and the migration is a no-op. (Verify the `PRAGMA index_list` row layout in a quick REPL if unsure: columns are `seq, name, unique, origin, partial`.)

- [ ] **Step 4: Run tests + full suite**

Run: `uv run pytest tests/api/test_database.py -q && uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/schema.py tests/api/test_database.py
git commit -m "feat(db): UNIQUE(local_path) on devcontainers with dedup migration"
```

---

### Task B3: `DevcontainerRepository.upsert`

**Files:**
- Modify: `src/vibing_api/repositories/devcontainers.py`
- Test: `tests/api/test_devcontainers_repository.py` (create if absent)

**Interfaces:**
- Consumes: `devcontainer_id` (B1).
- Produces: `DevcontainerRepository.upsert(name: str, local_path: str) -> DevcontainerRecord` — inserts with `id=devcontainer_id(local_path)`; on existing `local_path`, returns the existing row unchanged (name untouched).

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_devcontainers_repository.py
from pathlib import Path
import pytest
from vibing_api.core.database import get_connection, init_db
from vibing_api.repositories.devcontainers import DevcontainerRepository


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vibing_api.core.config import settings
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    init_db()


def test_upsert_inserts_then_is_idempotent_and_keeps_name() -> None:
    with get_connection() as conn:
        repo = DevcontainerRepository(conn)
        first = repo.upsert("My App", "/tmp/app")
        conn.commit()
        again = repo.upsert("Renamed", "/tmp/app")  # different name ignored
        conn.commit()
        rows = repo.list()
    assert again.id == first.id
    assert again.name == "My App"
    assert len([r for r in rows if r.local_path == "/tmp/app"]) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_devcontainers_repository.py -q`
Expected: FAIL (`AttributeError: ... 'upsert'`).

- [ ] **Step 3: Implement**

Add to `DevcontainerRepository` (import `devcontainer_id` from `vibing_api.core.discovery`):

```python
    def upsert(self, name: str, local_path: str) -> DevcontainerRecord:
        now = _now()
        self._conn.execute(
            f"INSERT INTO devcontainers ({_COLUMNS}) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(local_path) DO NOTHING",
            (devcontainer_id(local_path), name, local_path, now, now),
        )
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM devcontainers WHERE local_path = ?", (local_path,)
        ).fetchone()
        return _row(row)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_devcontainers_repository.py -q && uv run mypy src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/repositories/devcontainers.py tests/api/test_devcontainers_repository.py
git commit -m "feat(repo): idempotent DevcontainerRepository.upsert keyed on local_path"
```

---

### Task B4: Replace catalog with DB-only `DevcontainerStore`; drop `source`

**Files:**
- Create: `src/vibing_api/core/devcontainer_store.py`
- Delete: `src/vibing_api/core/catalog.py`, `tests/api/test_catalog.py` (if present)
- Modify: `src/vibing_api/main.py`, `src/vibing_api/api/routes/devcontainers.py`, `src/vibing_api/api/routes/harnesses.py`, `src/vibing_api/api/routes/delegated_runs.py`, `src/vibing_api/api/schemas/devcontainers.py`
- Test: `tests/api/test_devcontainers_api.py`, `tests/api/test_devcontainer_lifecycle.py`

**Interfaces:**
- Produces:
  - `DevcontainerStore(list_records, get_record)` with `.list() -> list[DevcontainerRecord]` and `.get(id) -> DevcontainerRecord | None` (thin DB pass-through; no scanner, no source).
  - `app.state.devcontainer_store` replaces `app.state.catalog`.
  - Routes use `DevcontainerRecord` (no `ResolvedDevcontainer`, no `source`).

- [ ] **Step 1: Write/adjust failing test**

In `tests/api/test_devcontainers_api.py`, add:

```python
def test_view_has_no_source_field(client: TestClient, fake_cli) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "n", "local_path": "/tmp/ns"}
    ).json()
    assert "source" not in created
    got = client.get(f"/api/v1/devcontainers/{created['id']}").json()
    assert "source" not in got
```

Remove or update any existing test asserting `source` (e.g. `test_*source*`) in this file and `test_devcontainer_lifecycle.py`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_devcontainers_api.py::test_view_has_no_source_field -q`
Expected: FAIL (`source` present).

- [ ] **Step 3: Implement**

Create `devcontainer_store.py`:

```python
"""DB-only devcontainer resolver (replaces the manual+discovered catalog).

After startup sync, every devcontainer is a real row; resolution is a plain DB read.
"""

from collections.abc import Callable

from vibing_api.repositories.devcontainers import DevcontainerRecord


class DevcontainerStore:
    def __init__(
        self,
        list_records: Callable[[], list[DevcontainerRecord]],
        get_record: Callable[[str], DevcontainerRecord | None],
    ) -> None:
        self._list_records = list_records
        self._get_record = get_record

    def list(self) -> list[DevcontainerRecord]:
        return self._list_records()

    def get(self, devcontainer_id: str) -> DevcontainerRecord | None:
        return self._get_record(devcontainer_id)
```

In `schemas/devcontainers.py`: delete `DevcontainerSource`; remove the `source` field from `Devcontainer`.

In `main.py`: remove the `DevcontainerCatalog`/`scan`/`load_devcontainers_dir`-for-catalog imports; build `app.state.devcontainer_store = DevcontainerStore(_list_records, _get_record)` using the existing `_list_records`/`_get_record` closures (drop the `scanner`).

In `devcontainers.py`: replace `from ...catalog import DevcontainerCatalog, ResolvedDevcontainer` with `from ...repositories.devcontainers import DevcontainerRecord`; change `_view`/`_teardown_container` signatures to take `DevcontainerRecord`; drop `source=resolved.source` from `DevcontainerView(...)`; replace every `request.app.state.catalog` with `request.app.state.devcontainer_store`; in `create_devcontainer` use `DevcontainerRepository(conn).upsert(...)` and resolve via the store; remove the `DevcontainerSource` import and the `if resolved.source == DevcontainerSource.MANUAL:` branch in `delete_devcontainer` (always delete the row). Remove the `DelegatedRunRepository` import/cleanup if still present (superseded by A4/A5).

In `harnesses.py` and `delegated_runs.py`: replace `request.app.state.catalog.get(...)` with `request.app.state.devcontainer_store.get(...)`.

```bash
git rm src/vibing_api/core/catalog.py
```

- [ ] **Step 4: Run full suite**

Run: `grep -rn "catalog\|ResolvedDevcontainer\|DevcontainerSource\|\.source" src/vibing_api` (expect no hits), then `uv run pytest -q && uv run ruff check src tests && uv run mypy src`.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(api): DB-only DevcontainerStore, drop catalog and source field"
```

---

### Task B5: Startup sync — `core/devcontainer_sync.py` wired into lifespan

**Files:**
- Create: `src/vibing_api/core/devcontainer_sync.py`
- Modify: `src/vibing_api/main.py` (`lifespan`)
- Test: `tests/api/test_devcontainer_sync.py`

**Interfaces:**
- Consumes: `scan`, `is_devcontainer_folder` (B1); `DevcontainerRepository.upsert`/`list`/`delete` (B3); `LiveStateStore` evictions (A1 + existing).
- Produces: `sync_devcontainers(devcontainers_dir: str | None, live_state: LiveStateStore) -> None` — upserts every scanned folder, then deletes every DB row whose `local_path` is not `is_devcontainer_folder`, evicting that id's live_state caches.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_devcontainer_sync.py
from pathlib import Path
import pytest
from vibing_api.core.database import get_connection, init_db
from vibing_api.core.devcontainer_sync import sync_devcontainers
from vibing_api.core.live_state import LiveStateStore
from vibing_api.repositories.devcontainers import DevcontainerRepository


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vibing_api.core.config import settings
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    init_db()


def _mk(root: Path, name: str) -> Path:
    d = root / name
    (d / ".devcontainer").mkdir(parents=True)
    return d


def test_sync_adds_new_evicts_missing(tmp_path: Path) -> None:
    root = tmp_path / "dcs"
    keep = _mk(root, "keep")
    live = LiveStateStore()

    sync_devcontainers(str(root), live)  # first sync: adds "keep"
    with get_connection() as conn:
        paths = {r.local_path for r in DevcontainerRepository(conn).list()}
    assert str(keep) in paths

    # Pre-seed live-state for a soon-to-be-stale manual row, then remove its folder
    gone = _mk(root, "gone")
    sync_devcontainers(str(root), live)
    with get_connection() as conn:
        gone_id = next(r.id for r in DevcontainerRepository(conn).list()
                       if r.local_path == str(gone))
    live.set_harness(gone_id, [])
    import shutil
    shutil.rmtree(gone)

    sync_devcontainers(str(root), live)  # evicts "gone"
    with get_connection() as conn:
        paths = {r.local_path for r in DevcontainerRepository(conn).list()}
    assert str(gone) not in paths
    assert str(keep) in paths
    assert live.get_harness(gone_id) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_devcontainer_sync.py -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement**

```python
# src/vibing_api/core/devcontainer_sync.py
"""Reconcile the devcontainers table with the filesystem at startup.

The filesystem is the source of truth for existence: upsert every scanned folder,
then evict any row whose path is no longer a devcontainer folder (manual rows
included). New folders surface after restart or via POST.
"""

from pathlib import Path

from vibing_api.core.database import get_connection
from vibing_api.core.discovery import is_devcontainer_folder, scan
from vibing_api.core.live_state import LiveStateStore
from vibing_api.repositories.devcontainers import DevcontainerRepository


def sync_devcontainers(devcontainers_dir: str | None, live_state: LiveStateStore) -> None:
    with get_connection() as conn:
        repo = DevcontainerRepository(conn)
        for found in scan(devcontainers_dir):
            repo.upsert(found.name, found.local_path)
        for record in repo.list():
            if not is_devcontainer_folder(Path(record.local_path)):
                repo.delete(record.id)
                live_state.clear_transient(record.id)
                live_state.clear_runtime_transient(record.id)
                live_state.evict_harness(record.id)
                live_state.evict_delegated_runs(record.id)
        conn.commit()
```

In `main.py` `lifespan`:

```python
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    sync_devcontainers(load_devcontainers_dir(), app.state.live_state)
    yield
```

(Use the `app` arg — rename `_app`→`app`; `app.state.live_state` is set in `create_app` before the app serves. Import `sync_devcontainers` and keep `load_devcontainers_dir`.)

- [ ] **Step 4: Run tests + full suite**

Run: `uv run pytest tests/api/test_devcontainer_sync.py -q && uv run pytest -q && uv run mypy src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/devcontainer_sync.py src/vibing_api/main.py tests/api/test_devcontainer_sync.py
git commit -m "feat(devcontainers): startup sync persists discovered, evicts stale"
```

---

### Task B6: Frontend — remove `source`

**Files:**
- Modify: `apps/web/src/lib/api/types.ts`, `apps/web/src/routes/DevcontainerDetail.tsx`, `apps/web/src/mock/state/devcontainers.ts`, `apps/web/src/mock/state/seeds.ts`
- Test: update `apps/web/src/mock/state/__tests__/devcontainers.test.ts`, `apps/web/src/mock/__tests__/devcontainers.test.ts`, `apps/web/src/routes/__tests__/Devcontainers.test.tsx`, `apps/web/src/routes/DevcontainerDetail.test.tsx`, `apps/web/src/components/__tests__/DevcontainerFormModal.test.tsx`, `apps/web/src/lib/api/__tests__/endpoints.test.ts`

- [ ] **Step 1: Update a failing test first**

In `apps/web/src/mock/state/__tests__/devcontainers.test.ts`, change the discovered-delete test to expect removal:

```ts
it('removes any devcontainer from the list on delete', () => {
  // (was: "keeps a discovered devcontainer ... resets status to stopped")
  const before = listDevcontainers().length
  deleteDevcontainer('dc-seed-0003')
  expect(listDevcontainers().some((d) => d.id === 'dc-seed-0003')).toBe(false)
  expect(listDevcontainers().length).toBe(before - 1)
})
```

- [ ] **Step 2: Run to verify it fails**

Run (in `apps/web`): `pnpm test -- devcontainers.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `types.ts`: delete `export type DevcontainerSource` and the `source` field on the devcontainer type.
- `DevcontainerDetail.tsx`: delete `SourceBadge` and its `<SourceBadge .../>` usage.
- `mock/state/devcontainers.ts`: remove `source` from the view mapper and the create default; delete the `if (dc.source === 'discovered') { ... }` branch in delete so it always removes.
- `seeds.ts`: drop `source` from each seed; remove the now-invalid discovered-only seed semantics (keep the rows, just no `source`).
- Update the remaining listed tests/fixtures to drop `source`.

- [ ] **Step 4: Run frontend tests**

Run (in `apps/web`): `pnpm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web
git commit -m "refactor(web): remove devcontainer source field"
```

---

### Task B7: Docs — ADR + CLAUDE.md coherence

**Files:**
- Create: `docs/adr/0020-discovered-devcontainers-are-persisted-via-startup-sync.md`
- Modify: `docs/adr/CLAUDE.md`, `src/vibing_api/CLAUDE.md`, `src/CLAUDE.md` (if it mentions discovered/virtual)

- [ ] **Step 1: Write the ADR**

Create `0020-…md` recording: discovered devcontainers are persisted as ordinary rows via a startup filesystem sync; the manual/discovered distinction, the `source` field, the read-time catalog merge, and the "virtual/never-persisted" model are removed. Consequences: new folders appear after restart/POST (not live); stale rows (folder gone) are evicted on startup, which can orphan a still-running container (killable via `docker rm -f`) — accepted to keep sync Docker-free. Status: accepted. Note it re-scopes the discovered-devcontainer behavior described in ADR-0001's neighborhood (0001 stays valid — source is still a single `local_path`).

- [ ] **Step 2: Update the ADR index**

Add the one-line `- [0020](…)` entry to `docs/adr/CLAUDE.md`.

- [ ] **Step 3: Update package CLAUDE.md**

In `src/vibing_api/CLAUDE.md`: delete the `core/catalog.py` bullet; update `core/discovery.py` to mention it feeds startup sync (not virtual merge); add `core/devcontainer_sync.py` and `core/devcontainer_store.py` bullets; update `core/live_state.py` to list the delegated-runs cache; update `core/runtime_intake.py` to "records delegated runs in-memory (no DB)"; update `delegated_runs.py` route bullet (serves from live-state now); update the `database.py/schema.py` bullet (no `delegated_runs` table; `devcontainers` has `UNIQUE(local_path)`); remove `source` mentions and the `manual | discovered` source language in Context.

- [ ] **Step 4: Verify references**

Run: `grep -rn "discovered\|virtual\|catalog\|source" src/vibing_api/CLAUDE.md src/CLAUDE.md` and confirm remaining mentions are accurate.

- [ ] **Step 5: Commit**

```bash
git add docs/adr src/vibing_api/CLAUDE.md src/CLAUDE.md
git commit -m "docs: ADR-0020 + CLAUDE.md coherence for devcontainer unification"
```

---

## Final verification

- [ ] `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
- [ ] `cd apps/web && pnpm test`
- [ ] `grep -rn "delegated_runs" src/vibing_api/repositories` returns nothing; `grep -rn "DevcontainerSource\|ResolvedDevcontainer\|catalog" src/vibing_api` returns nothing.
- [ ] Manual smoke (optional): start CP with a discovered folder configured, confirm it appears as a row, a runtime's delegated runs show at `GET …/delegated-runs`, and deleting the folder evicts the row on restart.
