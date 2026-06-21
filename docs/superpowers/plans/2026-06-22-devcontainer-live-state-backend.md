# Devcontainer Live-State & Discovery — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move devcontainer lifecycle status and harness status out of SQLite into live/in-memory sources, add config-driven folder discovery (never persisted), and add detail-view backend endpoints (delete-removes-container, manual inject-runtime).

**Architecture:** A `LiveStateStore` (in-memory, next to `RuntimeRegistry`) holds an ephemeral lifecycle-transient map and a push-cached harness-status map. A status resolver returns `starting`/`stopping`/`error` from the transient map, else `running`/`stopped` from a batched Docker query. A `DevcontainerCatalog` merges manual DB records with virtual discovered records (scanned from a configured folder, deduped by path, stable `uuid5` ids). Routes resolve every id through the catalog.

**Tech Stack:** Python 3.13, FastAPI, SQLite (stdlib `sqlite3`), pydantic v2, pydantic-settings, `pyyaml`, pytest. Shells out to `devcontainer`/`docker` CLIs (never SDKs).

## Global Constraints

- Never store in the DB anything retrievable live from the container engine or the Devcontainer Runtime (status, harness install/auth). Record metadata (`name`, `local_path`, `created_at`, `updated_at`) for manual records is fine.
- Shell out to `devcontainer`/`docker` CLIs only — never Docker/Podman SDKs (ADR-0003).
- Repositories execute SQL; callers commit.
- Use `logzero` for logging; `typer`+`rich` only for CLI (not relevant here).
- Checks must pass: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Dependency changes go through `uv` — never hand-edit `pyproject.toml`.

---

### Task 1: `LiveStateStore` — in-memory live state

**Files:**
- Create: `src/vibing_api/core/live_state.py`
- Test: `tests/api/test_live_state.py`

**Interfaces:**
- Consumes: `DevcontainerStatus` from `vibing_api.core.vocabularies`; `HarnessStatusItem` from `vibing_protocol`.
- Produces:
  ```python
  class LiveStateStore:
      def set_transient(self, devcontainer_id: str, status: DevcontainerStatus) -> None
      def clear_transient(self, devcontainer_id: str) -> None
      def get_transient(self, devcontainer_id: str) -> DevcontainerStatus | None
      def set_harness(self, devcontainer_id: str, items: list[HarnessStatusItem]) -> None
      def evict_harness(self, devcontainer_id: str) -> None
      def get_harness(self, devcontainer_id: str) -> list[HarnessStatusItem] | None
  ```

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_live_state.py
from vibing_protocol import HarnessStatusItem

from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.vocabularies import DevcontainerStatus


def test_transient_set_get_clear() -> None:
    store = LiveStateStore()
    assert store.get_transient("dc1") is None
    store.set_transient("dc1", DevcontainerStatus.STARTING)
    assert store.get_transient("dc1") == DevcontainerStatus.STARTING
    store.clear_transient("dc1")
    assert store.get_transient("dc1") is None


def test_clear_transient_is_idempotent() -> None:
    store = LiveStateStore()
    store.clear_transient("missing")  # no raise


def test_harness_cache_set_get_evict() -> None:
    store = LiveStateStore()
    assert store.get_harness("dc1") is None
    items = [HarnessStatusItem(name="codex", installed=True, authenticated=False)]
    store.set_harness("dc1", items)
    assert store.get_harness("dc1") == items
    store.evict_harness("dc1")
    assert store.get_harness("dc1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_live_state.py -q`
Expected: FAIL — `ModuleNotFoundError: vibing_api.core.live_state`

- [ ] **Step 3: Write minimal implementation**

```python
# src/vibing_api/core/live_state.py
"""In-memory live devcontainer state (ADR-0014 live-state model).

Holds two ephemeral maps keyed by devcontainer_id, alongside RuntimeRegistry:
- lifecycle transient (starting/stopping/error) during in-flight operations
- last harness-status the runtime pushed (evicted on disconnect → unknown)

Never persisted; lost on restart by design.
"""

from vibing_protocol import HarnessStatusItem

from vibing_api.core.vocabularies import DevcontainerStatus


class LiveStateStore:
    def __init__(self) -> None:
        self._transient: dict[str, DevcontainerStatus] = {}
        self._harness: dict[str, list[HarnessStatusItem]] = {}

    def set_transient(self, devcontainer_id: str, status: DevcontainerStatus) -> None:
        self._transient[devcontainer_id] = status

    def clear_transient(self, devcontainer_id: str) -> None:
        self._transient.pop(devcontainer_id, None)

    def get_transient(self, devcontainer_id: str) -> DevcontainerStatus | None:
        return self._transient.get(devcontainer_id)

    def set_harness(self, devcontainer_id: str, items: list[HarnessStatusItem]) -> None:
        self._harness[devcontainer_id] = items

    def evict_harness(self, devcontainer_id: str) -> None:
        self._harness.pop(devcontainer_id, None)

    def get_harness(self, devcontainer_id: str) -> list[HarnessStatusItem] | None:
        return self._harness.get(devcontainer_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_live_state.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/live_state.py tests/api/test_live_state.py
git commit -m "feat(api): add in-memory LiveStateStore for transient + harness state"
```

---

### Task 2: CLI adapter — `remove()` and `running_local_folders()`

**Files:**
- Modify: `src/vibing_api/core/devcontainer_cli.py`
- Test: `tests/api/test_devcontainer_cli.py` (add to existing if present, else create)

**Interfaces:**
- Consumes: existing `Runner`, `RunResult`, `DevcontainerSuccess`, `DevcontainerFailure`, `_missing_dir`.
- Produces, on `DevcontainerCliAdapter`:
  ```python
  async def remove(self, local_path: str) -> DevcontainerResult   # docker rm -f by label
  async def running_local_folders(self) -> set[str]               # one docker ps call
  ```

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_devcontainer_cli.py
import pytest

from vibing_api.core.devcontainer_cli import (
    DevcontainerCliAdapter,
    DevcontainerSuccess,
    RunResult,
)


def _fake_runner(script):
    calls = []

    async def run(command):
        calls.append(command)
        return script(command)

    run.calls = calls  # type: ignore[attr-defined]
    return run


@pytest.mark.anyio
async def test_remove_lists_by_label_then_force_removes(tmp_path) -> None:
    def script(cmd):
        if cmd[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "abc123\n", "")
        return RunResult(0, "", "")

    runner = _fake_runner(script)
    adapter = DevcontainerCliAdapter(runner=runner)
    result = await adapter.remove(str(tmp_path))

    assert isinstance(result, DevcontainerSuccess)
    assert ["docker", "rm", "-f", "abc123"] in runner.calls
    assert any(
        c[:3] == ["docker", "ps", "-q"]
        and f"label=devcontainer.local_folder={tmp_path}" in c
        for c in runner.calls
    )


@pytest.mark.anyio
async def test_remove_no_container_is_success(tmp_path) -> None:
    runner = _fake_runner(lambda cmd: RunResult(0, "", ""))
    adapter = DevcontainerCliAdapter(runner=runner)
    result = await adapter.remove(str(tmp_path))
    assert isinstance(result, DevcontainerSuccess)
    assert not any(c[:3] == ["docker", "rm", "-f"] for c in runner.calls)


@pytest.mark.anyio
async def test_running_local_folders_parses_label_lines() -> None:
    runner = _fake_runner(lambda cmd: RunResult(0, "/a/x\n\n/a/y\n", ""))
    adapter = DevcontainerCliAdapter(runner=runner)
    folders = await adapter.running_local_folders()
    assert folders == {"/a/x", "/a/y"}
```

If `tests/api/test_devcontainer_cli.py` does not exist, also ensure the `anyio` marker is available — the repo already runs async tests (see `test_devcontainer_service.py`); if it uses `asyncio.run`, mirror that instead of `@pytest.mark.anyio`. Confirm with: `grep -rn "anyio\|asyncio.run" tests/api`. If neither is configured, wrap calls with `asyncio.run(...)` and drop the markers.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_devcontainer_cli.py -q`
Expected: FAIL — `AttributeError: 'DevcontainerCliAdapter' object has no attribute 'remove'`

- [ ] **Step 3: Write minimal implementation**

Add to `DevcontainerCliAdapter` in `src/vibing_api/core/devcontainer_cli.py` (after `stop`):

```python
    async def remove(self, local_path: str) -> DevcontainerResult:
        if not Path(local_path).is_dir():
            return _missing_dir("remove", local_path)
        label = f"label=devcontainer.local_folder={local_path}"
        listed = await self._exec("remove", [self._engine, "ps", "-aq", "--filter", label])
        if isinstance(listed, DevcontainerFailure):
            return listed
        container_ids = listed.stdout.split()
        if not container_ids:
            return DevcontainerSuccess(operation="remove")
        removed = await self._exec("remove", [self._engine, "rm", "-f", *container_ids])
        if isinstance(removed, DevcontainerFailure):
            return removed
        return DevcontainerSuccess(operation="remove")

    async def running_local_folders(self) -> set[str]:
        command = [
            self._engine,
            "ps",
            "--filter",
            "label=devcontainer.local_folder",
            "--format",
            '{{index .Labels "devcontainer.local_folder"}}',
        ]
        result = await self._exec("running_local_folders", command)
        if isinstance(result, DevcontainerFailure):
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
```

Note: `remove` uses `ps -aq` (includes stopped containers) so a stopped devcontainer is also removed; the test asserts `ps -q` prefix which matches `["docker","ps","-q"...]` — update the test's slice to `cmd[:2] == ["docker", "ps"]` if you keep `-aq`. Keep test and impl consistent: use `ps -aq` in impl and assert `c[:2] == ["docker", "ps"]` in the test.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_devcontainer_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/devcontainer_cli.py tests/api/test_devcontainer_cli.py
git commit -m "feat(api): add CLI adapter remove() and running_local_folders()"
```

---

### Task 3: Live status resolver

**Files:**
- Create: `src/vibing_api/core/status_resolver.py`
- Test: `tests/api/test_status_resolver.py`

**Interfaces:**
- Consumes: `DevcontainerStatus`.
- Produces:
  ```python
  def resolve_status(
      transient: DevcontainerStatus | None,
      running_folders: set[str],
      local_path: str,
  ) -> DevcontainerStatus
  ```

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_status_resolver.py
from vibing_api.core.status_resolver import resolve_status
from vibing_api.core.vocabularies import DevcontainerStatus


def test_transient_wins_over_docker() -> None:
    assert (
        resolve_status(DevcontainerStatus.STARTING, {"/a"}, "/a")
        == DevcontainerStatus.STARTING
    )


def test_running_when_folder_present() -> None:
    assert resolve_status(None, {"/a", "/b"}, "/a") == DevcontainerStatus.RUNNING


def test_stopped_when_folder_absent() -> None:
    assert resolve_status(None, {"/b"}, "/a") == DevcontainerStatus.STOPPED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_status_resolver.py -q`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# src/vibing_api/core/status_resolver.py
"""Live devcontainer status: in-flight transient wins, else live Docker truth."""

from vibing_api.core.vocabularies import DevcontainerStatus


def resolve_status(
    transient: DevcontainerStatus | None,
    running_folders: set[str],
    local_path: str,
) -> DevcontainerStatus:
    if transient is not None:
        return transient
    if local_path in running_folders:
        return DevcontainerStatus.RUNNING
    return DevcontainerStatus.STOPPED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_status_resolver.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/status_resolver.py tests/api/test_status_resolver.py
git commit -m "feat(api): add live devcontainer status resolver"
```

---

### Task 4: Vocabulary — drop `CREATED`

**Files:**
- Modify: `src/vibing_api/core/vocabularies.py`
- Modify: `apps/web/src/lib/api/types.ts` (string-union must match; frontend plan also touches it — make the enum change here, type union there)
- Test: `tests/api/test_status_resolver.py` already covers running/stopped; add a guard test below.

**Interfaces:**
- Produces: `DevcontainerStatus` without `CREATED`. Members: `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `ERROR`.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_vocabularies.py
from vibing_api.core.vocabularies import DevcontainerStatus


def test_created_status_removed() -> None:
    assert not hasattr(DevcontainerStatus, "CREATED")
    assert {s.value for s in DevcontainerStatus} == {
        "starting",
        "running",
        "stopping",
        "stopped",
        "error",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_vocabularies.py -q`
Expected: FAIL — `CREATED` still present

- [ ] **Step 3: Write minimal implementation**

```python
# src/vibing_api/core/vocabularies.py
from enum import StrEnum, auto


class DevcontainerStatus(StrEnum):
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_vocabularies.py -q`
Expected: PASS. (Other modules referencing `CREATED` will now fail to import — fixed in Tasks 5 & 9. Do not run the full suite yet.)

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/vocabularies.py tests/api/test_vocabularies.py
git commit -m "refactor(api): drop CREATED status (folds into stopped, live model)"
```

---

### Task 5: Schema + repository — drop `status` column and `harness_status` table

**Files:**
- Modify: `src/vibing_api/core/schema.py`
- Modify: `src/vibing_api/repositories/devcontainers.py`
- Delete: `src/vibing_api/repositories/harness_status.py`
- Modify: `src/vibing_api/api/schemas/devcontainers.py`
- Test: `tests/api/test_devcontainers_api.py` (update), `tests/api/test_schema_migration.py` (create)

**Interfaces:**
- Produces:
  - `devcontainers` table columns: `id, name, local_path, created_at, updated_at` (no `status`).
  - `harness_status` table removed; `HarnessStatusRepository` deleted.
  - `DevcontainerRepository.create/list/get/update/delete` no longer reference `status`.
  - API schema `Devcontainer` gains `source: DevcontainerSource` and `status: DevcontainerStatus` (status is set by the route from the resolver, not the repo). Repository returns a new `DevcontainerRecord` (no status).

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_schema_migration.py
import sqlite3

from vibing_api.core.schema import apply_schema


def test_devcontainers_has_no_status_column(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "t.db")
    apply_schema(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(devcontainers)")}
    assert cols == {"id", "name", "local_path", "created_at", "updated_at"}


def test_harness_status_table_removed(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "t.db")
    apply_schema(conn)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "harness_status" not in tables


def test_migration_drops_legacy_status_and_table(tmp_path) -> None:
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE devcontainers (id TEXT PRIMARY KEY, name TEXT, local_path TEXT, "
        "status TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.execute("CREATE TABLE harness_status (devcontainer_id TEXT, name TEXT)")
    conn.commit()
    apply_schema(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(devcontainers)")}
    assert "status" not in cols
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "harness_status" not in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_schema_migration.py -q`
Expected: FAIL — `status` column present, `harness_status` exists

- [ ] **Step 3: Write minimal implementation**

In `src/vibing_api/core/schema.py`: bump version, drop `status` from the `devcontainers` CREATE, remove the `harness_status` CREATE and its index, and add migration drops.

```python
SCHEMA_VERSION = "8"
```

Replace the `devcontainers` CREATE statement body with:
```python
    """
    CREATE TABLE IF NOT EXISTS devcontainers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        local_path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
```
Remove the entire `harness_status` CREATE statement from `_TABLE_STATEMENTS`, and remove the `idx_harness_status_devcontainer` line from `_INDEX_STATEMENTS`.

Add a migration helper and call it from `apply_schema` before `_migrate_schema`:
```python
def _drop_legacy(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS harness_status")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(devcontainers)")}
    if "status" in cols:
        conn.execute("ALTER TABLE devcontainers DROP COLUMN status")
```
```python
def apply_schema(conn: sqlite3.Connection) -> None:
    for statement in _TABLE_STATEMENTS:
        conn.execute(statement)
    for statement in _INDEX_STATEMENTS:
        conn.execute(statement)
    _drop_legacy(conn)
    _migrate_schema(conn)
```
(`ALTER TABLE ... DROP COLUMN` requires SQLite ≥ 3.35, present in Python 3.13 builds.)

Delete the repository file:
```bash
git rm src/vibing_api/repositories/harness_status.py
```

Rewrite `src/vibing_api/api/schemas/devcontainers.py`:
```python
from enum import StrEnum, auto

from pydantic import BaseModel, Field

from vibing_api.core.vocabularies import DevcontainerStatus


class DevcontainerSource(StrEnum):
    MANUAL = auto()
    DISCOVERED = auto()


class DevcontainerCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    local_path: str = Field(min_length=1)


class DevcontainerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)


class Devcontainer(BaseModel):
    id: str
    name: str
    local_path: str
    status: DevcontainerStatus
    source: DevcontainerSource
    created_at: str | None
    updated_at: str | None


class DevcontainerList(BaseModel):
    items: list[Devcontainer]


class RuntimeConnection(BaseModel):
    runtime_connected: bool


class DevcontainerView(Devcontainer):
    runtime: RuntimeConnection


class DevcontainerViewList(BaseModel):
    items: list[DevcontainerView]
```
Note: `DevcontainerUpdateRequest` loses `status` (status is no longer settable). The PATCH route (Task 8) updates `name` only.

Rewrite `src/vibing_api/repositories/devcontainers.py` to drop status and return a plain record:
```python
"""Devcontainer persistence (manual records only). Repository executes; caller commits."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

_COLUMNS = "id, name, local_path, created_at, updated_at"


@dataclass(frozen=True)
class DevcontainerRecord:
    id: str
    name: str
    local_path: str
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r: sqlite3.Row) -> DevcontainerRecord:
    return DevcontainerRecord(
        id=r["id"],
        name=r["name"],
        local_path=r["local_path"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class DevcontainerRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def create(self, name: str, local_path: str) -> DevcontainerRecord:
        devcontainer_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            f"INSERT INTO devcontainers ({_COLUMNS}) VALUES (?, ?, ?, ?, ?)",
            (devcontainer_id, name, local_path, now, now),
        )
        return DevcontainerRecord(devcontainer_id, name, local_path, now, now)

    def list(self) -> list[DevcontainerRecord]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM devcontainers ORDER BY created_at"
        ).fetchall()
        return [_row(r) for r in rows]

    def get(self, devcontainer_id: str) -> DevcontainerRecord | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM devcontainers WHERE id = ?", (devcontainer_id,)
        ).fetchone()
        return _row(row) if row is not None else None

    def update(self, devcontainer_id: str, *, name: str | None = None) -> DevcontainerRecord | None:
        current = self.get(devcontainer_id)
        if current is None:
            return None
        if name is None:
            return current
        self._conn.execute(
            "UPDATE devcontainers SET name = ?, updated_at = ? WHERE id = ?",
            (name, _now(), devcontainer_id),
        )
        return self.get(devcontainer_id)

    def delete(self, devcontainer_id: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM devcontainers WHERE id = ?", (devcontainer_id,)
        )
        return cursor.rowcount > 0
```

- [ ] **Step 4: Run the migration test to verify it passes**

Run: `uv run pytest tests/api/test_schema_migration.py -q`
Expected: PASS. (Routes/services still reference old types — fixed in Tasks 8–12. Full suite will be green by Task 12.)

- [ ] **Step 5: Commit**

```bash
git add -A src/vibing_api/core/schema.py src/vibing_api/repositories/ src/vibing_api/api/schemas/devcontainers.py tests/api/test_schema_migration.py
git commit -m "refactor(api): drop status column + harness_status table; add source"
```

---

### Task 6: Config file loader (`vibing.yaml`)

**Files:**
- Create: `src/vibing_api/core/file_config.py`
- Modify: `pyproject.toml` via `uv add pyyaml` (and `uv add --dev types-pyyaml`)
- Test: `tests/api/test_file_config.py`

**Interfaces:**
- Consumes: `settings.database_url` from `vibing_api.core.config`.
- Produces:
  ```python
  def config_file_path() -> Path          # override env VIBING_CONFIG_FILE, else sibling of vibing.db
  def load_devcontainers_dir() -> str | None  # None when file/key absent
  ```

- [ ] **Step 1: Add dependency**

Run:
```bash
uv add pyyaml
uv add --dev types-pyyaml
```
Expected: `pyproject.toml` updated by uv; `pyyaml` importable.

- [ ] **Step 2: Write the failing test**

```python
# tests/api/test_file_config.py
from pathlib import Path

import pytest

from vibing_api.core import file_config


def test_returns_none_when_file_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIBING_CONFIG_FILE", str(tmp_path / "nope.yaml"))
    assert file_config.load_devcontainers_dir() is None


def test_reads_devcontainers_dir(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "vibing.yaml"
    cfg.write_text("devcontainers_dir: /srv/devcontainers\n")
    monkeypatch.setenv("VIBING_CONFIG_FILE", str(cfg))
    assert file_config.load_devcontainers_dir() == "/srv/devcontainers"


def test_missing_key_returns_none(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "vibing.yaml"
    cfg.write_text("other: 1\n")
    monkeypatch.setenv("VIBING_CONFIG_FILE", str(cfg))
    assert file_config.load_devcontainers_dir() is None


def test_default_path_is_sibling_of_db(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("VIBING_CONFIG_FILE", raising=False)
    monkeypatch.setattr(
        file_config.settings, "database_url", f"sqlite:///{tmp_path / 'vibing.db'}"
    )
    assert file_config.config_file_path() == tmp_path / "vibing.yaml"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/api/test_file_config.py -q`
Expected: FAIL — module not found

- [ ] **Step 4: Write minimal implementation**

```python
# src/vibing_api/core/file_config.py
"""Optional YAML config file (sibling of vibing.db, or VIBING_CONFIG_FILE).

Currently exposes only `devcontainers_dir` used by folder discovery. Absent
file or key → None → discovery off.
"""

import os
from pathlib import Path

import yaml

from vibing_api.core.config import settings


def config_file_path() -> Path:
    override = os.environ.get("VIBING_CONFIG_FILE")
    if override:
        return Path(override)
    db = settings.database_url.removeprefix("sqlite:///")
    return Path(db).parent / "vibing.yaml"


def load_devcontainers_dir() -> str | None:
    path = config_file_path()
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text()) or {}
    value = data.get("devcontainers_dir") if isinstance(data, dict) else None
    return str(value) if value else None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/api/test_file_config.py -q`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add -A pyproject.toml uv.lock src/vibing_api/core/file_config.py tests/api/test_file_config.py
git commit -m "feat(api): add optional vibing.yaml config loader (devcontainers_dir)"
```

---

### Task 7: Discovery scanner

**Files:**
- Create: `src/vibing_api/core/discovery.py`
- Test: `tests/api/test_discovery.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  ```python
  @dataclass(frozen=True)
  class DiscoveredDevcontainer:
      id: str
      name: str
      local_path: str

  def discovered_id(local_path: str) -> str          # stable uuid5
  def scan(devcontainers_dir: str | None) -> list[DiscoveredDevcontainer]
  ```

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_discovery.py
from vibing_api.core.discovery import discovered_id, scan


def _make_dc(parent, name, with_dotdir=True):
    d = parent / name
    d.mkdir()
    if with_dotdir:
        (d / ".devcontainer").mkdir()
    return d


def test_scan_none_dir_is_empty() -> None:
    assert scan(None) == []


def test_scan_missing_dir_is_empty(tmp_path) -> None:
    assert scan(str(tmp_path / "missing")) == []


def test_scan_finds_only_dirs_with_dotdevcontainer(tmp_path) -> None:
    _make_dc(tmp_path, "alpha")
    _make_dc(tmp_path, "beta")
    _make_dc(tmp_path, "plain", with_dotdir=False)
    (tmp_path / "afile").write_text("x")

    found = {d.name: d for d in scan(str(tmp_path))}
    assert set(found) == {"alpha", "beta"}
    assert found["alpha"].local_path == str(tmp_path / "alpha")


def test_scan_is_not_recursive(tmp_path) -> None:
    outer = _make_dc(tmp_path, "outer")
    _make_dc(outer, "inner")  # nested; must be ignored
    assert {d.name for d in scan(str(tmp_path))} == {"outer"}


def test_id_is_stable_for_path() -> None:
    assert discovered_id("/a/b") == discovered_id("/a/b")
    assert discovered_id("/a/b") != discovered_id("/a/c")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_discovery.py -q`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# src/vibing_api/core/discovery.py
"""Folder discovery of devcontainers (virtual, never persisted).

Non-recursive scan of a configured directory: each immediate subdirectory that
contains a `.devcontainer/` folder is one devcontainer. Stable uuid5 id keyed on
the absolute local_path so start/stop/inject/harness/runtime-WS all agree.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


@dataclass(frozen=True)
class DiscoveredDevcontainer:
    id: str
    name: str
    local_path: str


def discovered_id(local_path: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, local_path))


def scan(devcontainers_dir: str | None) -> list[DiscoveredDevcontainer]:
    if not devcontainers_dir:
        return []
    root = Path(devcontainers_dir)
    if not root.is_dir():
        return []
    out: list[DiscoveredDevcontainer] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / ".devcontainer").is_dir():
            continue
        path = str(child)
        out.append(DiscoveredDevcontainer(discovered_id(path), child.name, path))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_discovery.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/discovery.py tests/api/test_discovery.py
git commit -m "feat(api): add non-recursive devcontainer folder discovery"
```

---

### Task 8: `DevcontainerCatalog` — merge manual + discovered

**Files:**
- Create: `src/vibing_api/core/catalog.py`
- Test: `tests/api/test_catalog.py`

**Interfaces:**
- Consumes: `DevcontainerRepository` + `DevcontainerRecord` (Task 5), `scan`/`DiscoveredDevcontainer` (Task 7), `DevcontainerSource` (Task 5).
- Produces:
  ```python
  @dataclass(frozen=True)
  class ResolvedDevcontainer:
      id: str
      name: str
      local_path: str
      source: DevcontainerSource
      created_at: str | None
      updated_at: str | None

  class DevcontainerCatalog:
      def __init__(self, repo_factory, scanner)  # scanner: () -> list[DiscoveredDevcontainer]
      def list(self) -> list[ResolvedDevcontainer]
      def get(self, devcontainer_id: str) -> ResolvedDevcontainer | None
  ```
  Dedup: a manual record with the same `local_path` as a discovered one hides the discovered one.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_catalog.py
from vibing_api.api.schemas.devcontainers import DevcontainerSource
from vibing_api.core.catalog import DevcontainerCatalog
from vibing_api.core.discovery import DiscoveredDevcontainer, discovered_id
from vibing_api.repositories.devcontainers import DevcontainerRecord


class FakeRepo:
    def __init__(self, records):
        self._records = records

    def list(self):
        return list(self._records)

    def get(self, devcontainer_id):
        return next((r for r in self._records if r.id == devcontainer_id), None)


def _manual(id_, path):
    return DevcontainerRecord(id_, "manual-" + id_, path, "t0", "t1")


def test_list_merges_and_tags_source() -> None:
    repo = _manual("m1", "/a")
    disc = DiscoveredDevcontainer(discovered_id("/b"), "b", "/b")
    cat = DevcontainerCatalog(lambda: FakeRepo([repo]), lambda: [disc])
    by_id = {r.id: r for r in cat.list()}
    assert by_id["m1"].source == DevcontainerSource.MANUAL
    assert by_id[disc.id].source == DevcontainerSource.DISCOVERED
    assert by_id[disc.id].created_at is None


def test_manual_hides_discovered_with_same_path() -> None:
    repo = _manual("m1", "/shared")
    disc = DiscoveredDevcontainer(discovered_id("/shared"), "shared", "/shared")
    cat = DevcontainerCatalog(lambda: FakeRepo([repo]), lambda: [disc])
    items = cat.list()
    assert [r.id for r in items] == ["m1"]


def test_get_resolves_manual_and_discovered() -> None:
    repo = _manual("m1", "/a")
    disc = DiscoveredDevcontainer(discovered_id("/b"), "b", "/b")
    cat = DevcontainerCatalog(lambda: FakeRepo([repo]), lambda: [disc])
    assert cat.get("m1").source == DevcontainerSource.MANUAL
    assert cat.get(disc.id).source == DevcontainerSource.DISCOVERED
    assert cat.get("missing") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_catalog.py -q`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# src/vibing_api/core/catalog.py
"""Unified read over manual (DB) + discovered (folder) devcontainers.

Discovered records are virtual. Dedup by local_path: a manual record hides a
discovered one at the same path. Backs get(id) for every lifecycle route so
discovered ids resolve instead of 404ing.
"""

from collections.abc import Callable
from dataclasses import dataclass

from vibing_api.api.schemas.devcontainers import DevcontainerSource
from vibing_api.core.discovery import DiscoveredDevcontainer
from vibing_api.repositories.devcontainers import DevcontainerRecord


@dataclass(frozen=True)
class ResolvedDevcontainer:
    id: str
    name: str
    local_path: str
    source: DevcontainerSource
    created_at: str | None
    updated_at: str | None


class _Repo:
    def list(self) -> list[DevcontainerRecord]: ...
    def get(self, devcontainer_id: str) -> DevcontainerRecord | None: ...


class DevcontainerCatalog:
    def __init__(
        self,
        repo_factory: Callable[[], _Repo],
        scanner: Callable[[], list[DiscoveredDevcontainer]],
    ) -> None:
        self._repo_factory = repo_factory
        self._scanner = scanner

    def list(self) -> list[ResolvedDevcontainer]:
        manual = [self._from_record(r) for r in self._repo_factory().list()]
        taken = {r.local_path for r in manual}
        discovered = [
            self._from_discovered(d) for d in self._scanner() if d.local_path not in taken
        ]
        return manual + discovered

    def get(self, devcontainer_id: str) -> ResolvedDevcontainer | None:
        record = self._repo_factory().get(devcontainer_id)
        if record is not None:
            return self._from_record(record)
        for d in self._scanner():
            if d.id == devcontainer_id:
                return self._from_discovered(d)
        return None

    @staticmethod
    def _from_record(r: DevcontainerRecord) -> ResolvedDevcontainer:
        return ResolvedDevcontainer(
            r.id, r.name, r.local_path, DevcontainerSource.MANUAL, r.created_at, r.updated_at
        )

    @staticmethod
    def _from_discovered(d: DiscoveredDevcontainer) -> ResolvedDevcontainer:
        return ResolvedDevcontainer(
            d.id, d.name, d.local_path, DevcontainerSource.DISCOVERED, None, None
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_catalog.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/catalog.py tests/api/test_catalog.py
git commit -m "feat(api): add DevcontainerCatalog merging manual + discovered"
```

---

### Task 9: Rewrite `DevcontainerService` for live transient status (no DB status, no auto-inject)

**Files:**
- Modify: `src/vibing_api/core/devcontainer_service.py`
- Modify: `tests/api/test_devcontainer_service.py`

**Interfaces:**
- Consumes: `LiveStateStore` (Task 1), `DevcontainerCliAdapter` (Task 2), `Broadcaster`.
- Produces:
  ```python
  class DevcontainerService:
      def __init__(self, adapter, *, live_state: LiveStateStore, broadcaster: Broadcaster | None = None)
      async def start(self, devcontainer_id: str, local_path: str) -> None
      async def stop(self, devcontainer_id: str, local_path: str) -> None
  ```
  No injector, no repo writes. `start`: set transient STARTING → broadcast → `adapter.start` → on success clear transient (Docker now reports running) + broadcast; on failure set transient ERROR + broadcast. `stop`: transient STOPPING → `adapter.stop` → clear on success / ERROR on failure, broadcast each edge. Runtime injection is no longer triggered here.

- [ ] **Step 1: Rewrite the service test**

```python
# tests/api/test_devcontainer_service.py
import asyncio

from vibing_api.core.devcontainer_cli import DevcontainerFailure, DevcontainerSuccess
from vibing_api.core.devcontainer_service import DevcontainerService
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.vocabularies import DevcontainerStatus


class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def start(self, local_path):
        self.calls.append(("start", local_path))
        return self.result

    async def stop(self, local_path):
        self.calls.append(("stop", local_path))
        return DevcontainerSuccess(operation="stop")


class FakeBroadcaster:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def test_start_sets_then_clears_transient_on_success() -> None:
    live = LiveStateStore()
    bc = FakeBroadcaster()
    svc = DevcontainerService(
        FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"})),
        live_state=live,
        broadcaster=bc,
    )
    asyncio.run(svc.start("dc1", "/path"))
    assert live.get_transient("dc1") is None  # cleared → live Docker truth
    assert [e.scope for e in bc.events] == ["devcontainers", "devcontainers"]


def test_start_failure_sets_error_transient() -> None:
    live = LiveStateStore()
    svc = DevcontainerService(
        FakeAdapter(
            DevcontainerFailure(
                operation="start", command=[], exit_code=1, stderr_tail="", message="boom"
            )
        ),
        live_state=live,
    )
    asyncio.run(svc.start("dc1", "/path"))
    assert live.get_transient("dc1") == DevcontainerStatus.ERROR


def test_stop_clears_transient_on_success() -> None:
    live = LiveStateStore()
    svc = DevcontainerService(
        FakeAdapter(DevcontainerSuccess(operation="start")), live_state=live
    )
    asyncio.run(svc.stop("dc1", "/path"))
    assert live.get_transient("dc1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_devcontainer_service.py -q`
Expected: FAIL — `DevcontainerService.__init__` signature mismatch / injector references

- [ ] **Step 3: Rewrite the implementation**

```python
# src/vibing_api/core/devcontainer_service.py
"""In-process Devcontainer lifecycle (ADR-0014, live-state model).

Shells out to the Dev Container CLI; reflects in-flight status in the in-memory
LiveStateStore (no DB status). Runtime injection is now an explicit endpoint, not
an automatic post-start step. Long ops run in a background task; routes return 202.
"""

import asyncio

from logzero import logger

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.devcontainer_cli import DevcontainerCliAdapter, DevcontainerFailure
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.vocabularies import DevcontainerStatus


class DevcontainerService:
    def __init__(
        self,
        adapter: DevcontainerCliAdapter,
        *,
        live_state: LiveStateStore,
        broadcaster: Broadcaster | None = None,
    ) -> None:
        self._adapter = adapter
        self._live = live_state
        self._broadcaster = broadcaster

    def _publish(self, devcontainer_id: str) -> None:
        if self._broadcaster is not None:
            self._broadcaster.publish(SseEvent(scope="devcontainers", ids=[devcontainer_id]))

    def _set(self, devcontainer_id: str, status: DevcontainerStatus) -> None:
        self._live.set_transient(devcontainer_id, status)
        self._publish(devcontainer_id)

    def _clear(self, devcontainer_id: str) -> None:
        self._live.clear_transient(devcontainer_id)
        self._publish(devcontainer_id)

    async def start(self, devcontainer_id: str, local_path: str) -> None:
        self._set(devcontainer_id, DevcontainerStatus.STARTING)
        result = await self._adapter.start(local_path)
        if isinstance(result, DevcontainerFailure):
            logger.error("devcontainer start failed (%s): %s", devcontainer_id, result.message)
            self._set(devcontainer_id, DevcontainerStatus.ERROR)
            return
        self._clear(devcontainer_id)

    async def stop(self, devcontainer_id: str, local_path: str) -> None:
        self._set(devcontainer_id, DevcontainerStatus.STOPPING)
        result = await self._adapter.stop(local_path)
        if isinstance(result, DevcontainerFailure):
            logger.error("devcontainer stop failed (%s): %s", devcontainer_id, result.message)
            self._set(devcontainer_id, DevcontainerStatus.ERROR)
            return
        self._clear(devcontainer_id)


def run_in_background(coro) -> "asyncio.Task[None]":
    return asyncio.create_task(coro)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_devcontainer_service.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/devcontainer_service.py tests/api/test_devcontainer_service.py
git commit -m "refactor(api): drive devcontainer status via LiveStateStore, drop auto-inject"
```

---

### Task 10: Harness status via in-memory cache (intake + WS + route)

**Files:**
- Modify: `src/vibing_api/core/runtime_intake.py`
- Modify: `src/vibing_api/api/routes/runtime.py`
- Modify: `src/vibing_api/api/routes/harnesses.py`
- Test: `tests/api/test_harnesses_api.py` (update/create), `tests/api/test_runtime_ws.py` (if present — update)

**Interfaces:**
- Consumes: `LiveStateStore` (Task 1) via `app.state.live_state` (wired in Task 13).
- Produces:
  - `runtime_intake.record_harness_status(live: LiveStateStore, devcontainer_id, items, broadcaster)` replaces `persist_harness_status` (DB write removed).
  - `GET /{id}/harnesses` returns the cached items; unknown (no cache entry) → `installed=None`/`authenticated=None` per item is not possible (no items), so when the cache is absent the endpoint returns `{"items": [], "known": false}`; when present returns `{"items": [...], "known": true}`.
  - WS `harness_status` handler writes to the cache; WS unregister evicts the cache.

**Note on "unknown":** The frontend renders `?` when `known` is `false`. The harness *names* themselves come from the runtime, so with no runtime connected there are no rows to show per-harness — hence a top-level `known` flag rather than per-row tri-state.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_harnesses_api.py
from vibing_protocol import HarnessStatusItem

from vibing_api.core.runtime_intake import record_harness_status
from vibing_api.core.live_state import LiveStateStore


def test_list_harnesses_unknown_when_no_cache(client, devcontainer_id) -> None:
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "known": False}


def test_list_harnesses_known_after_runtime_push(client, devcontainer_id) -> None:
    live: LiveStateStore = client.app.state.live_state
    record_harness_status(
        live,
        devcontainer_id,
        [HarnessStatusItem(name="codex", installed=True, authenticated=False)],
        None,
    )
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    body = resp.json()
    assert body["known"] is True
    assert body["items"] == [{"name": "codex", "installed": True, "authenticated": False}]


def test_record_harness_status_evict(client, devcontainer_id) -> None:
    live: LiveStateStore = client.app.state.live_state
    record_harness_status(
        live, devcontainer_id, [HarnessStatusItem(name="codex", installed=True, authenticated=True)], None
    )
    live.evict_harness(devcontainer_id)
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.json()["known"] is False
```

Also update `src/vibing_api/api/schemas/harnesses.py` — add `known: bool` to `HarnessStatusList`:
```python
class HarnessStatusList(BaseModel):
    items: list[HarnessStatusItem]
    known: bool = False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_harnesses_api.py -q`
Expected: FAIL — `record_harness_status` missing / `known` field absent

- [ ] **Step 3: Write minimal implementation**

In `src/vibing_api/core/runtime_intake.py`, replace `persist_harness_status` with:
```python
from vibing_api.core.live_state import LiveStateStore


def record_harness_status(
    live: LiveStateStore,
    devcontainer_id: str,
    items: list[HarnessStatusItem],
    broadcaster: Broadcaster | None = None,
) -> None:
    live.set_harness(devcontainer_id, items)
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="harnesses", ids=[devcontainer_id]))
```
Remove the `HarnessStatusRepository` import and the old function. Keep `persist_delegated_runs` unchanged.

In `src/vibing_api/api/routes/runtime.py`:
- Replace the `harness_status` branch body to use the cache:
```python
            if msg_type == "harness_status":
                try:
                    envelope = HarnessStatusEnvelope.model_validate(message)
                except ValidationError:
                    continue
                live = websocket.app.state.live_state
                broadcaster = getattr(websocket.app.state, "broadcaster", None)
                record_harness_status(live, envelope.devcontainer_id, envelope.items, broadcaster)
                continue
```
- Update the import: `from vibing_api.core.runtime_intake import persist_delegated_runs, record_harness_status`.
- In the `agent_ws` `unregister` closure, evict the cache:
```python
        def unregister() -> None:
            manager.unregister(devcontainer_id, connection)
            websocket.app.state.live_state.evict_harness(devcontainer_id)
            _broadcast_connection(websocket, ids=[devcontainer_id])
```

Rewrite `GET /{id}/harnesses` in `src/vibing_api/api/routes/harnesses.py`:
```python
from vibing_api.core.live_state import LiveStateStore


@router.get("/{devcontainer_id}/harnesses", response_model=HarnessStatusList)
def list_harnesses(devcontainer_id: str, request: Request) -> HarnessStatusList:
    live: LiveStateStore = request.app.state.live_state
    cached = live.get_harness(devcontainer_id)
    if cached is None:
        return HarnessStatusList(items=[], known=False)
    return HarnessStatusList(
        items=[
            HarnessStatusItem(name=i.name, installed=i.installed, authenticated=i.authenticated)
            for i in cached
        ],
        known=True,
    )
```
Remove the now-unused imports (`get_connection`, `DevcontainerRepository`, `HarnessStatusRepository`) from `harnesses.py`. The `install`/`authenticate` handlers stay as-is (they check `runtime_manager.is_connected` and send commands). Note `HarnessStatusItem` in `vibing_api.api.schemas.harnesses` and `vibing_protocol.HarnessStatusItem` are distinct; the route uses the API-schema one — keep that import.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/api/test_harnesses_api.py -q`
Expected: PASS (3 tests). (Requires `app.state.live_state` — wired in Task 13. Until then, run after Task 13, or temporarily set it in a fixture. Mark these tests `xfail` is NOT allowed; instead reorder: do Task 13 wiring before running. See note.)

> **Sequencing note:** Tasks 9–12 mutate `app.state` wiring that Task 13 finalizes. Implement Tasks 9–12 code, then do Task 13, then run the API-level tests in 10/11/12. The pure-unit tests (1–8) pass independently as written.

- [ ] **Step 5: Commit**

```bash
git add -A src/vibing_api/core/runtime_intake.py src/vibing_api/api/routes/runtime.py src/vibing_api/api/routes/harnesses.py src/vibing_api/api/schemas/harnesses.py tests/api/test_harnesses_api.py
git commit -m "refactor(api): serve harness status from in-memory cache, evict on disconnect"
```

---

### Task 11: Devcontainer routes — live status, source, catalog-backed get/list

**Files:**
- Modify: `src/vibing_api/api/routes/devcontainers.py`
- Test: `tests/api/test_devcontainers_api.py` (update)

**Interfaces:**
- Consumes: `DevcontainerCatalog` (Task 8) via `app.state.catalog`, `LiveStateStore` via `app.state.live_state`, `DevcontainerCliAdapter` via `app.state.devcontainer_cli` (wired Task 13), `resolve_status` (Task 3).
- Produces: `GET ""` and `GET /{id}` return `DevcontainerView` with computed `status` + `source`; create still returns a manual record (status computed); start/stop dispatch via catalog-resolved `local_path`; PATCH updates name only.

- [ ] **Step 1: Update the API test**

```python
# tests/api/test_devcontainers_api.py  (representative additions/changes)
def test_create_then_list_shows_source_and_status(client) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "demo", "local_path": "/tmp/demo"}
    ).json()
    assert created["source"] == "manual"
    assert created["status"] == "stopped"  # no container running

    listed = client.get("/api/v1/devcontainers").json()["items"]
    row = next(r for r in listed if r["id"] == created["id"])
    assert row["source"] == "manual"
    assert row["status"] == "stopped"


def test_get_unknown_id_404(client) -> None:
    resp = client.get("/api/v1/devcontainers/nope")
    assert resp.status_code == 404
```

For the live-status assertions, the CLI adapter's `running_local_folders` must be stubbed so no real Docker is called. In `conftest.py`, override `app.state.devcontainer_cli` with a fake exposing `async def running_local_folders(self) -> set[str]: return self.running` and `async def remove(...)`. Add a fixture:
```python
# tests/api/conftest.py (add)
class FakeCli:
    def __init__(self) -> None:
        self.running: set[str] = set()
        self.removed: list[str] = []

    async def running_local_folders(self) -> set[str]:
        return self.running

    async def remove(self, local_path: str):
        from vibing_api.core.devcontainer_cli import DevcontainerSuccess
        self.removed.append(local_path)
        return DevcontainerSuccess(operation="remove")


@pytest.fixture
def fake_cli(client) -> "FakeCli":
    cli = FakeCli()
    client.app.state.devcontainer_cli = cli
    return cli
```
And a test using it:
```python
def test_status_running_when_docker_reports_folder(client, fake_cli) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "r", "local_path": "/tmp/r"}
    ).json()
    fake_cli.running = {"/tmp/r"}
    row = next(
        r for r in client.get("/api/v1/devcontainers").json()["items"]
        if r["id"] == created["id"]
    )
    assert row["status"] == "running"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_devcontainers_api.py -q`
Expected: FAIL — `source` missing / status from removed column

- [ ] **Step 3: Rewrite the routes**

```python
# src/vibing_api/api/routes/devcontainers.py
from fastapi import APIRouter, Request, Response, status

from vibing_api.api.schemas.devcontainers import (
    Devcontainer,
    DevcontainerCreateRequest,
    DevcontainerUpdateRequest,
    DevcontainerView,
    DevcontainerViewList,
    RuntimeConnection,
)
from vibing_api.core.catalog import DevcontainerCatalog, ResolvedDevcontainer
from vibing_api.core.database import get_connection
from vibing_api.core.devcontainer_service import DevcontainerService, run_in_background
from vibing_api.core.errors import DevcontainerNotFoundError, InvalidDevcontainerStateError
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.status_resolver import resolve_status
from vibing_api.core.vocabularies import DevcontainerStatus
from vibing_api.repositories.devcontainers import DevcontainerRepository

router = APIRouter(tags=["devcontainers"], prefix="/devcontainers")

_START_ALLOWED_FROM = frozenset(
    {DevcontainerStatus.STOPPED, DevcontainerStatus.ERROR}
)
_STOP_ALLOWED_FROM = frozenset({DevcontainerStatus.RUNNING, DevcontainerStatus.ERROR})


async def _view(resolved: ResolvedDevcontainer, request: Request) -> DevcontainerView:
    live: LiveStateStore = request.app.state.live_state
    running = await request.app.state.devcontainer_cli.running_local_folders()
    status_value = resolve_status(
        live.get_transient(resolved.id), running, resolved.local_path
    )
    runtime = RuntimeConnection(
        runtime_connected=request.app.state.runtime_manager.is_connected(resolved.id)
    )
    return DevcontainerView(
        id=resolved.id,
        name=resolved.name,
        local_path=resolved.local_path,
        status=status_value,
        source=resolved.source,
        created_at=resolved.created_at,
        updated_at=resolved.updated_at,
        runtime=runtime,
    )


@router.post("", response_model=Devcontainer, status_code=status.HTTP_201_CREATED)
async def create_devcontainer(payload: DevcontainerCreateRequest, request: Request) -> Devcontainer:
    with get_connection() as conn:
        record = DevcontainerRepository(conn).create(payload.name, payload.local_path)
        conn.commit()
    catalog: DevcontainerCatalog = request.app.state.catalog
    resolved = catalog.get(record.id)
    assert resolved is not None
    return await _view(resolved, request)


@router.get("", response_model=DevcontainerViewList)
async def list_devcontainers(request: Request) -> DevcontainerViewList:
    catalog: DevcontainerCatalog = request.app.state.catalog
    views = [await _view(r, request) for r in catalog.list()]
    return DevcontainerViewList(items=views)


@router.get("/{devcontainer_id}", response_model=DevcontainerView)
async def get_devcontainer(devcontainer_id: str, request: Request) -> DevcontainerView:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    return await _view(resolved, request)


@router.patch("/{devcontainer_id}", response_model=Devcontainer)
async def update_devcontainer(
    devcontainer_id: str, payload: DevcontainerUpdateRequest, request: Request
) -> Devcontainer:
    with get_connection() as conn:
        updated = DevcontainerRepository(conn).update(devcontainer_id, name=payload.name)
        conn.commit()
    if updated is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    resolved = request.app.state.catalog.get(devcontainer_id)
    assert resolved is not None
    return await _view(resolved, request)


@router.post("/{devcontainer_id}/start", response_model=DevcontainerView, status_code=202)
async def start_devcontainer(devcontainer_id: str, request: Request) -> DevcontainerView:
    return await _dispatch_lifecycle(devcontainer_id, request, "start", _START_ALLOWED_FROM)


@router.post("/{devcontainer_id}/stop", response_model=DevcontainerView, status_code=202)
async def stop_devcontainer(devcontainer_id: str, request: Request) -> DevcontainerView:
    return await _dispatch_lifecycle(devcontainer_id, request, "stop", _STOP_ALLOWED_FROM)


async def _dispatch_lifecycle(
    devcontainer_id: str,
    request: Request,
    action: str,
    allowed_from: frozenset[DevcontainerStatus],
) -> DevcontainerView:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    view = await _view(resolved, request)
    if view.status not in allowed_from:
        raise InvalidDevcontainerStateError(action, view.status, allowed_from)
    service: DevcontainerService = request.app.state.devcontainer_service
    coro = (
        service.start(resolved.id, resolved.local_path)
        if action == "start"
        else service.stop(resolved.id, resolved.local_path)
    )
    run_in_background(coro)
    return view


@router.delete("/{devcontainer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_devcontainer(devcontainer_id: str, request: Request) -> Response:
    return await _delete_impl(devcontainer_id, request)  # implemented in Task 12
```

> The `delete` body is fully written in **Task 12** (it needs `remove()`); leave the call to `_delete_impl` and add that function in Task 12. To keep this task self-contained and green, temporarily inline a minimal delete here and replace it in Task 12 — OR implement Task 12 immediately after Step 3 here before running tests. Recommended: do Task 12 Step 3 now, then run both test files together.

- [ ] **Step 4: Run test to verify it passes** (after Task 12 + Task 13 wiring)

Run: `uv run pytest tests/api/test_devcontainers_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/api/routes/devcontainers.py tests/api/test_devcontainers_api.py tests/api/conftest.py
git commit -m "feat(api): compute live status + source in devcontainer routes via catalog"
```

---

### Task 12: Delete removes container; manual inject-runtime endpoint

**Files:**
- Modify: `src/vibing_api/api/routes/devcontainers.py`
- Modify: `src/vibing_api/core/runtime_injector.py`
- Test: `tests/api/test_devcontainers_api.py`, `tests/api/test_runtime_injector.py` (update/create)

**Interfaces:**
- Consumes: `DevcontainerCliAdapter.remove` (Task 2), `RuntimeInjector`, catalog.
- Produces:
  - `DELETE /{id}` — kills+removes the container (`cli.remove(local_path)`), then for `source=manual` deletes the DB row; for `discovered` no DB action. Returns 204. Evicts harness cache + clears transient.
  - `POST /{id}/inject-runtime` (202) — resolves container_id from `local_path` and runs the injector in background.
  - `RuntimeInjector.inject_by_path(devcontainer_id, local_path)` — resolves the container id via the `devcontainer.local_folder` label, then runs existing `inject`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_devcontainers_api.py (add)
def test_delete_manual_removes_container_and_record(client, fake_cli) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "d", "local_path": "/tmp/d"}
    ).json()
    resp = client.delete(f"/api/v1/devcontainers/{created['id']}")
    assert resp.status_code == 204
    assert "/tmp/d" in fake_cli.removed
    assert client.get(f"/api/v1/devcontainers/{created['id']}").status_code == 404


def test_delete_unknown_404(client, fake_cli) -> None:
    assert client.delete("/api/v1/devcontainers/nope").status_code == 404
```

```python
# tests/api/test_runtime_injector.py (add)
import asyncio

from vibing_api.core.devcontainer_cli import RunResult
from vibing_api.core.runtime_injector import RuntimeInjector


def test_inject_by_path_resolves_container_then_injects() -> None:
    calls = []

    async def runner(command):
        calls.append(command)
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir="/nonexistent")
    # wheel_dir missing → inject() returns early after resolving; we assert resolve happened
    asyncio.run(injector.inject_by_path("dc1", "/work/repo"))
    assert any(
        c[:3] == ["docker", "ps", "-q"]
        and "label=devcontainer.local_folder=/work/repo" in c
        for c in calls
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_runtime_injector.py -q`
Expected: FAIL — `inject_by_path` missing

- [ ] **Step 3: Implement**

Add to `RuntimeInjector` in `src/vibing_api/core/runtime_injector.py`:
```python
    async def resolve_container_id(self, local_path: str) -> str | None:
        label = f"label=devcontainer.local_folder={local_path}"
        try:
            result = await self._runner([self._engine, "ps", "-q", "--filter", label])
        except FileNotFoundError:
            return None
        if result.returncode != 0:
            return None
        ids = result.stdout.split()
        return ids[0] if ids else None

    async def inject_by_path(self, devcontainer_id: str, local_path: str) -> None:
        container_id = await self.resolve_container_id(local_path)
        if container_id is None:
            logger.warning("inject: no running container for %s (%s)", devcontainer_id, local_path)
            return
        await self.inject(devcontainer_id, container_id, local_path)
```

In `src/vibing_api/api/routes/devcontainers.py`, implement the delete and inject endpoint:
```python
async def _delete_impl(devcontainer_id: str, request: Request) -> Response:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    await request.app.state.devcontainer_cli.remove(resolved.local_path)
    live: LiveStateStore = request.app.state.live_state
    live.clear_transient(resolved.id)
    live.evict_harness(resolved.id)
    if resolved.source == DevcontainerSource.MANUAL:
        with get_connection() as conn:
            DevcontainerRepository(conn).delete(resolved.id)
            conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{devcontainer_id}/inject-runtime", status_code=202)
async def inject_runtime(devcontainer_id: str, request: Request) -> dict:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    injector = request.app.state.runtime_injector
    run_in_background(injector.inject_by_path(resolved.id, resolved.local_path))
    return {}
```
Add `DevcontainerSource` to the imports from `vibing_api.api.schemas.devcontainers`.

- [ ] **Step 4: Run tests to verify they pass** (after Task 13 wiring)

Run: `uv run pytest tests/api/test_runtime_injector.py tests/api/test_devcontainers_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/api/routes/devcontainers.py src/vibing_api/core/runtime_injector.py tests/api/test_runtime_injector.py tests/api/test_devcontainers_api.py
git commit -m "feat(api): delete removes container; add manual inject-runtime endpoint"
```

---

### Task 13: Wire app state (`create_app`) + conftest

**Files:**
- Modify: `src/vibing_api/main.py`
- Modify: `tests/api/conftest.py`
- Test: full suite

**Interfaces:**
- Produces on `app.state`: `runtime_manager`, `broadcaster`, `live_state`, `devcontainer_cli`, `runtime_injector`, `catalog`, `devcontainer_service`.

- [ ] **Step 1: Update `create_app`**

```python
# src/vibing_api/main.py  (replace the create_app body wiring block)
from vibing_api.core.catalog import DevcontainerCatalog
from vibing_api.core.database import get_connection
from vibing_api.core.discovery import scan
from vibing_api.core.file_config import load_devcontainers_dir
from vibing_api.core.live_state import LiveStateStore
from vibing_api.repositories.devcontainers import DevcontainerRepository
```
```python
def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.runtime_manager = RuntimeRegistry()
    app.state.broadcaster = Broadcaster()
    app.state.live_state = LiveStateStore()
    app.state.devcontainer_cli = DevcontainerCliAdapter()
    app.state.runtime_injector = RuntimeInjector()

    def _repo_factory():
        # short-lived connection per call; catalog reads only
        conn = get_connection().__enter__()
        return DevcontainerRepository(conn)

    app.state.catalog = DevcontainerCatalog(
        repo_factory=lambda: _list_repo(),
        scanner=lambda: scan(load_devcontainers_dir()),
    )
    app.state.devcontainer_service = DevcontainerService(
        app.state.devcontainer_cli,
        live_state=app.state.live_state,
        broadcaster=app.state.broadcaster,
    )
    register_error_handlers(app)
    for router in (...):  # unchanged list
        app.include_router(router, prefix=settings.api_v1_prefix)
    if settings.static_dir:
        app.mount("/", SpaStaticFiles(directory=settings.static_dir, html=True), name="static")
    return app
```

> The `repo_factory` must hand the catalog a repo backed by a real connection and ensure the connection closes. Cleanest: give the catalog a factory that opens, reads, and closes per call. Implement a tiny helper instead of the `__enter__` hack:
```python
# src/vibing_api/core/catalog.py — add a DB-backed repo factory used by main
from contextlib import contextmanager

def db_repo_snapshot() -> list[DevcontainerRecord]:
    ...
```
Prefer this: change `DevcontainerCatalog` to accept `list_records: Callable[[], list[DevcontainerRecord]]` and `get_record: Callable[[str], DevcontainerRecord | None]` instead of a `repo_factory`, so `main` can pass functions that manage their own connections:
```python
# main.py
def _list_records():
    with get_connection() as conn:
        return DevcontainerRepository(conn).list()

def _get_record(devcontainer_id: str):
    with get_connection() as conn:
        return DevcontainerRepository(conn).get(devcontainer_id)

app.state.catalog = DevcontainerCatalog(
    list_records=_list_records,
    get_record=_get_record,
    scanner=lambda: scan(load_devcontainers_dir()),
)
```
Update `DevcontainerCatalog.__init__` and `list`/`get` accordingly, and update `tests/api/test_catalog.py` to pass `list_records`/`get_record` lambdas over a fake list. (Adjust the Task 8 `FakeRepo` test to `DevcontainerCatalog(list_records=lambda: records, get_record=lambda i: ..., scanner=...)`.)

- [ ] **Step 2: Update conftest**

Ensure `client` fixture sets a stub CLI so no real Docker runs in API tests by default:
```python
# tests/api/conftest.py
@pytest.fixture
def client(db_path):
    from vibing_api.main import create_app
    app = create_app()
    app.state.devcontainer_cli = FakeCli()  # defined in Task 11
    with TestClient(app) as c:
        yield c
```
(If the existing `client` fixture differs, set `app.state.devcontainer_cli = FakeCli()` after `create_app()` and before `TestClient`.)

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (all tests green, including Tasks 10–12 API tests).

- [ ] **Step 4: Lint, format, type-check**

Run:
```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```
Expected: clean. Fix any issues (e.g. unused imports left behind in `harnesses.py`/`runtime.py`).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/main.py tests/api/conftest.py src/vibing_api/core/catalog.py tests/api/test_catalog.py
git commit -m "feat(api): wire live-state, catalog, discovery into app + tests green"
```

---

### Task 14: Backend docs coherence

**Files:**
- Modify: `src/vibing_api/CLAUDE.md`
- Modify: `src/CLAUDE.md` (if package responsibilities shifted)
- Modify: any ADR referenced by the touched files (search `docs/` for ADR-0014/0016 mentions of harness_status persistence and devcontainer status)

**Interfaces:** docs only.

- [ ] **Step 1: Update `src/vibing_api/CLAUDE.md`**

Update the Files/Context sections to reflect:
- `core/live_state.py` — in-memory transient lifecycle status + harness-status cache (evicted on disconnect).
- `core/status_resolver.py` — live status (transient else Docker label).
- `core/discovery.py` + `core/file_config.py` — `vibing.yaml` folder discovery (virtual, non-recursive).
- `core/catalog.py` — merges manual (DB) + discovered, dedup by path.
- `devcontainer_service.py` — no longer writes DB status or auto-injects runtime.
- `runtime_intake.py` — harness status now cached in memory (no `harness_status` table).
- routes: `inject-runtime` endpoint; `delete` removes the container.
- Remove the `harness_status` table from any schema description; note `devcontainers` has no `status` column.

- [ ] **Step 2: Grep for stale references**

Run:
```bash
grep -rn "harness_status\|HarnessStatusRepository\|DevcontainerStatus.CREATED\|persist_harness_status" src docs
```
Expected: no stale references in `src`. Update any `docs/adr/*` lines that describe persisting harness status or devcontainer status as read-model writes — add a short note that these became live/in-memory (cite this plan's date).

- [ ] **Step 3: Final checks**

Run:
```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q
```
Expected: all clean/green.

- [ ] **Step 4: Commit**

```bash
git add -A src docs
git commit -m "docs(api): update CLAUDE.md + ADRs for live-state model and discovery"
```

---

## Self-Review

**Spec coverage:**
- Live status, no DB → Tasks 1,3,4,5,9,11 ✓
- Harness status in-memory, `?` unknown, evict on disconnect → Tasks 1,10 ✓
- `vibing.yaml` discovery, virtual, non-recursive, derived id, dedup → Tasks 6,7,8 ✓
- Unified resolver → Task 8 ✓
- Delete kills+removes (manual removes row, discovered reappears) → Task 12 ✓
- Manual inject endpoint + remove auto-inject → Tasks 9,12 ✓
- `source` field → Tasks 5,8,11 ✓
- Docs coherence → Task 14 ✓
- Frontend (icons, spinner, `?` render, mock, Playwright) → **Plan 2** (separate file).

**Known sequencing constraint:** Tasks 9–12 finalize against the `app.state` wiring in Task 13; implement 9–13 as a block, then run the API-level tests. Pure-unit tests (1–8) are independently green. This is called out inline in Tasks 10 and 11.

**Type consistency:** `DevcontainerRecord` (repo, no status) vs `ResolvedDevcontainer` (catalog, +source/+timestamps nullable) vs `Devcontainer`/`DevcontainerView` (API, +status computed). `DevcontainerCatalog` final signature is `list_records`/`get_record`/`scanner` (Task 13 supersedes the Task 8 `repo_factory` sketch — Task 13 says to update Task 8's test). `HarnessStatusList` gains `known: bool`.
