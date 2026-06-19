# Collapse Runtimes into the Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Host Runtime Worker, the event-sourcing layer, and the entire Agent Session subsystem; the Control Plane drives Devcontainers directly in-process and the Devcontainer Runtime becomes a harness-friction companion (harness management + MCP), with per-container Harness Status shown in the web.

**Architecture:** Two reversals, captured in [ADR-0014](../../adr/0014-the-control-plane-drives-devcontainers-directly-and-the-event-log-is-removed.md) and [ADR-0015](../../adr/0015-drop-the-agent-session-model-the-devcontainer-runtime-is-a-harness-friction-companion.md). (1) The backend shells out to the Dev Container CLI in-process behind a background task and writes devcontainer status directly — no `runtime_events` log, no reducer, no host worker. (2) The Agent Session model is deleted end to end; the in-container runtime keeps only harness management + the MCP delegation server, reporting Harness Status up over a slimmed WebSocket channel.

**Tech Stack:** Python 3.13, FastAPI, SQLite (stdlib `sqlite3`), Pydantic, Typer, `websockets`, `pytest`, `ruff`, `mypy`. Frontend: React + Vite + TS + Tailwind, vitest, MSW.

## Global Constraints

- Python checks (repo root): `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`. All must pass at the end of every task.
- Frontend checks (`apps/web/`): `pnpm test`, `pnpm build`.
- Use `uv` for any dependency change; never hand-edit `pyproject.toml` deps.
- Domain language is canonical in `CONTEXT.md`: "Devcontainer Runtime" (never "agent"/"worker"), "Harness Status", "Harness Credentials", "Delegated Run". The Agent Session vocabulary is retired — do not reintroduce it.
- StrEnum vocabularies: compare/construct with members, not raw strings.
- One coding-harness-status decision stands: Delegated Runs are **in-container only** (not tracked by the backend). Per-container Harness Status **is** tracked by the backend.
- Commit after every task. Keep commits scoped to one task.

## Phasing & green-between-commits note

This is a teardown-then-rebuild. Phase 1 deletes the dead subsystems in **consumer-before-producer** order so the suite stays green per task — **except** the devcontainer start/stop path, which depends on the host worker and is therefore deliberately left broken at the end of Task 1.6 and restored in Phase 2. Each task says explicitly whether the full suite is green or whether a named set of tests is expected red until a later task. Do not "fix" an expected-red test by reviving deleted code.

---

## File Structure (end state)

```
src/
  vibing_api/
    core/
      devcontainer_cli.py        # MOVED from vibing_host_runtime (verbatim)
      runtime_injector.py        # MOVED from vibing_host_runtime/agent_launcher.py (renamed)
      devcontainer_service.py    # NEW: in-process lifecycle (direct CLI + background task + direct status)
      runtime_channel.py         # SLIMMED: agent-only registry + harness_status intake
      broadcaster.py             # unchanged
      config.py, database.py, schema.py, errors.py, vocabularies.py, commands.py
    repositories/
      devcontainers.py           # unchanged
      harness_status.py          # NEW
    api/
      routes/  devcontainers.py harnesses.py runtime.py events.py config.py health.py status.py settings.py diagnostics.py
      schemas/ devcontainers.py harnesses.py common.py
    cli/dev.py, main.py
  vibing_devcontainer_runtime/
    runtime_client.py            # MOVED from vibing_runtime_client/client.py (folded in)
    cli.py                       # SLIMMED: harness mgmt + MCP only; reports harness_status
    command_handler.py           # SLIMMED: authenticate_harness only
    harness/*, harness_manager.py, delegated_runs.py, mcp_server.py   # unchanged
  vibing_protocol/
    commands.py                  # SLIMMED: AUTHENTICATE_HARNESS only
    messages.py                  # SLIMMED: register + command + harness_status
    __init__.py                  # SLIMMED exports
  vibing_cli/
    __init__.py                  # SLIMMED: dev, runtime devcontainer, devcontainer, system
    client/ devcontainers.py http.py render.py system.py harnesses.py
DELETED packages: vibing_host_runtime/, vibing_runtime_client/
DELETED protocol module: runtime_events.py, claude_output.py (Claude stream parsing)
```

---

# Phase 1 — Cleanup

### Task 1.1: Delete the Inbox & Approvals subsystem (backend + CLI + frontend)

The frontend strip already removed Inbox/Approvals UI; this removes the now-orphaned backend and CLI halves. Pure deletion; nothing surviving imports these once the reducer is trimmed (Task 1.5 handles the reducer — until then the reducer still references inbox/approval repos, so delete the **routes, schemas, CLI** here and the **repos** in Task 1.5).

**Files:**
- Delete: `src/vibing_api/api/routes/inbox.py`, `src/vibing_api/api/routes/approvals.py`
- Delete: `src/vibing_api/api/schemas/inbox.py`, `src/vibing_api/api/schemas/approvals.py`
- Delete: `src/vibing_cli/client/inbox.py`, `src/vibing_cli/client/approvals.py`
- Delete: `tests/api/test_inbox_approvals.py`, `tests/api/test_inbox_read_resolved.py`, `tests/api/test_intervention_error_contract.py`, `tests/cli/test_inbox_approvals_system.py`
- Modify: `src/vibing_api/main.py` (drop `inbox`, `approvals` from the import tuple and `include_router` loop)
- Modify: `src/vibing_cli/__init__.py` (drop `inbox`, `approvals` imports + `add_typer` lines)

- [ ] **Step 1: Delete the files listed above.**

```bash
git rm src/vibing_api/api/routes/inbox.py src/vibing_api/api/routes/approvals.py \
  src/vibing_api/api/schemas/inbox.py src/vibing_api/api/schemas/approvals.py \
  src/vibing_cli/client/inbox.py src/vibing_cli/client/approvals.py \
  tests/api/test_inbox_approvals.py tests/api/test_inbox_read_resolved.py \
  tests/api/test_intervention_error_contract.py tests/cli/test_inbox_approvals_system.py
```

- [ ] **Step 2: Remove `inbox` and `approvals` from `main.py`.** In `src/vibing_api/main.py`, delete `inbox,` and `approvals,` from the `from vibing_api.api.routes import (...)` block and remove `inbox.router,` and `approvals.router,` from the `include_router` tuple.

- [ ] **Step 3: Remove inbox/approval mounts from the CLI.** In `src/vibing_cli/__init__.py`, delete `inbox` and `approvals` from the `from vibing_cli.client import ...` line and delete the two lines `app.add_typer(inbox.app, name="inbox")` and `app.add_typer(approvals.app, name="approval")`.

- [ ] **Step 4: Run checks.**

Run: `uv run ruff check src tests && uv run mypy src && uv run pytest -q`
Expected: PASS. (The reducer still references inbox/approval *repositories*, which still exist — they are deleted in Task 1.5. Routes/schemas/CLI for inbox/approvals are gone with no remaining importers.)

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit -m "chore: remove inbox & approvals backend + cli"
```

---

### Task 1.2: Delete the Agent Session HTTP/SSE surface (routes, schemas, session stream)

**Files:**
- Delete: `src/vibing_api/api/routes/agent_sessions.py`, `src/vibing_api/api/routes/session_stream.py`
- Delete: `src/vibing_api/api/schemas/agent_sessions.py`
- Delete: `src/vibing_api/core/session_stream.py`
- Delete: `tests/api/test_agent_sessions.py`, `tests/api/test_agent_session_transcript.py`, `tests/api/test_session_stream_buffer.py`, `tests/api/test_session_stream_registry.py`, `tests/api/test_session_stream_sse.py`, `tests/api/test_turn_delta_relay.py`
- Modify: `src/vibing_api/main.py` (drop `agent_sessions`, `session_stream` imports, routers, and `app.state.session_streams`)
- Modify: `src/vibing_api/api/routes/runtime.py` (drop the `relay_delta`/`resolve_transcript`/`session_streams` wiring in `agent_ws` — keep only register + the soon-to-be `harness_status` intake; the transcript/turn_delta branches go in Task 1.6 when the protocol types are removed, but their *agent-route wiring* can be removed now)

- [ ] **Step 1: Delete the files.**

```bash
git rm src/vibing_api/api/routes/agent_sessions.py src/vibing_api/api/routes/session_stream.py \
  src/vibing_api/api/schemas/agent_sessions.py src/vibing_api/core/session_stream.py \
  tests/api/test_agent_sessions.py tests/api/test_agent_session_transcript.py \
  tests/api/test_session_stream_buffer.py tests/api/test_session_stream_registry.py \
  tests/api/test_session_stream_sse.py tests/api/test_turn_delta_relay.py
```

- [ ] **Step 2: Trim `main.py`.** Remove `agent_sessions,` and `session_stream,` from the routes import and the `include_router` tuple. Remove the line `from vibing_api.core.session_stream import SessionStreamRegistry` and the line `app.state.session_streams = SessionStreamRegistry()`.

- [ ] **Step 3: Trim the agent WS route.** In `src/vibing_api/api/routes/runtime.py`, in `agent_ws`, delete the `session_streams = getattr(...)` lookup and the `relay_delta` closure, and call `_serve(websocket, register)` (drop `resolve_transcript=` and `relay_delta=` kwargs). Leave `_serve` itself for Task 1.6.

- [ ] **Step 4: Run checks.**

Run: `uv run pytest -q tests/api`
Expected: PASS except tests that import the now-removed transcript/turn-delta protocol types are still fine (those types still exist until Task 1.6). `tests/api/test_runtime_channel.py` and `test_agent_channel.py` may reference transcript RPC — if they fail here, that is expected-red; note it and proceed (they are deleted/rewritten in Task 1.6).

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit -m "chore: remove agent-session http + session-stream surface"
```

---

### Task 1.3: Delete the Agent Session runner from the Devcontainer Runtime

**Files:**
- Delete: `src/vibing_devcontainer_runtime/claude_runner.py`, `stream_normalizer.py`, `transcript.py`, `content_blocks.py`, `running_sessions.py`
- Delete: `tests/devcontainer_runtime/test_claude_runner.py`, `test_stream_normalizer.py`, `test_transcript_parser.py`, `test_command_handler.py`
- Keep: `test_command_handler_harness.py` (harness path), `test_delegated_runs.py`, `test_mcp_server.py`, `test_harness_*`, `test_codex_adapter.py`, `test_cursor_adapter.py`, `test_cli.py`
- Modify: `src/vibing_devcontainer_runtime/command_handler.py` (rewritten in Task 3.2; for now it still imports `claude_runner`/`running_sessions`)

This task deletes the files but `command_handler.py` and `cli.py` still import them, so the runtime package won't import until Task 3.2. Sequence: do the command_handler rewrite (Task 3.2) and cli rewrite (Task 3.3) immediately after if running inline; under subagent-driven execution, mark `tests/devcontainer_runtime` expected-red until Phase 3.

- [ ] **Step 1: Delete the files.**

```bash
git rm src/vibing_devcontainer_runtime/claude_runner.py \
  src/vibing_devcontainer_runtime/stream_normalizer.py \
  src/vibing_devcontainer_runtime/transcript.py \
  src/vibing_devcontainer_runtime/content_blocks.py \
  src/vibing_devcontainer_runtime/running_sessions.py \
  tests/devcontainer_runtime/test_claude_runner.py \
  tests/devcontainer_runtime/test_stream_normalizer.py \
  tests/devcontainer_runtime/test_transcript_parser.py \
  tests/devcontainer_runtime/test_command_handler.py
```

- [ ] **Step 2: Run import check (expected partial failure).**

Run: `uv run pytest -q tests/devcontainer_runtime/test_harness_manager.py tests/devcontainer_runtime/test_delegated_runs.py`
Expected: PASS (these don't import the deleted modules). The package-level `command_handler`/`cli` import is broken until Phase 3 — that is expected.

- [ ] **Step 3: Commit.**

```bash
git add -A && git commit -m "chore: remove agent-session runner from devcontainer runtime"
```

---

### Task 1.4: Delete the `vibing_host_runtime` and `vibing_runtime_client` packages

`vibing_host_runtime` is replaced by in-process logic (Phase 2); `vibing_runtime_client` is folded into the runtime (Phase 3). Move the two files we keep **before** deleting the packages so history is clean.

**Files:**
- Move: `src/vibing_host_runtime/devcontainer_cli.py` → `src/vibing_api/core/devcontainer_cli.py`
- Move: `src/vibing_host_runtime/agent_launcher.py` → `src/vibing_api/core/runtime_injector.py`
- Move: `src/vibing_host_runtime/agent_url.py` → `src/vibing_api/core/runtime_injector_url.py` (or inline into `runtime_injector.py`)
- Move: `src/vibing_runtime_client/client.py` → `src/vibing_devcontainer_runtime/runtime_client.py`
- Delete: the rest of `src/vibing_host_runtime/` and all of `src/vibing_runtime_client/`
- Delete: `tests/host_runtime/` (whole dir), `tests/runtime_client/` (whole dir)
- Move test: `tests/host_runtime/test_devcontainer_cli.py` → `tests/api/test_devcontainer_cli.py` (update imports to `vibing_api.core.devcontainer_cli`)

- [ ] **Step 1: Move the kept files (preserve content, fix imports later).**

```bash
git mv src/vibing_host_runtime/devcontainer_cli.py src/vibing_api/core/devcontainer_cli.py
git mv src/vibing_host_runtime/agent_launcher.py src/vibing_api/core/runtime_injector.py
git mv src/vibing_host_runtime/agent_url.py src/vibing_api/core/runtime_injector_url.py
git mv src/vibing_runtime_client/client.py src/vibing_devcontainer_runtime/runtime_client.py
git mv tests/host_runtime/test_devcontainer_cli.py tests/api/test_devcontainer_cli.py
```

- [ ] **Step 2: Delete the remaining package + test files.**

```bash
git rm -r src/vibing_host_runtime src/vibing_runtime_client tests/host_runtime tests/runtime_client
```

- [ ] **Step 3: Fix imports in the moved files.**
  - `src/vibing_api/core/runtime_injector.py`: change `from vibing_host_runtime.agent_url import resolve_agent_control_plane_url` → `from vibing_api.core.runtime_injector_url import resolve_agent_control_plane_url`; change `from vibing_host_runtime.devcontainer_cli import Runner, _default_runner` → `from vibing_api.core.devcontainer_cli import Runner, _default_runner`.
  - `tests/api/test_devcontainer_cli.py`: change `from vibing_host_runtime.devcontainer_cli import ...` → `from vibing_api.core.devcontainer_cli import ...`.
  - `src/vibing_devcontainer_runtime/runtime_client.py`: no internal import changes (it only imports `vibing_protocol`).

- [ ] **Step 4: Run check (devcontainer_cli test only).**

Run: `uv run pytest -q tests/api/test_devcontainer_cli.py`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit -m "chore: move host-runtime cli adapter + injector into backend; fold runtime-client into runtime; delete dead packages"
```

---

### Task 1.5: Delete the event-sourcing layer (reducer, runtime_events, summaries, inbox/approval repos)

**Files:**
- Delete: `src/vibing_api/core/reducer.py`
- Delete: `src/vibing_api/repositories/runtime_events.py`, `src/vibing_api/repositories/summaries.py`, `src/vibing_api/repositories/inbox.py`, `src/vibing_api/repositories/approvals.py`, `src/vibing_api/repositories/agent_sessions.py`
- Delete: `tests/api/test_reducer.py`, `tests/api/test_runtime_events.py`, `tests/api/test_repositories.py` (rewrite the devcontainer-repo portion into a new slim test if it covers devcontainers — see Step 3)
- Modify: `src/vibing_api/core/runtime_channel.py` — remove `persist_runtime_event`, the reducer import, and `RuntimeEventRepository` usage. (`AgentRegistry` stays but loses the transcript RPC in Task 1.6.)
- Modify: `src/vibing_api/core/vocabularies.py` — delete `AgentSessionStatus`, `ApprovalStatus`, `InboxEventType`, `InboxEventStatus`; keep `DevcontainerStatus`. Add `HarnessStatusField` only if needed (Harness Status is booleans, so no enum needed).

- [ ] **Step 1: Delete the files.**

```bash
git rm src/vibing_api/core/reducer.py \
  src/vibing_api/repositories/runtime_events.py src/vibing_api/repositories/summaries.py \
  src/vibing_api/repositories/inbox.py src/vibing_api/repositories/approvals.py \
  src/vibing_api/repositories/agent_sessions.py \
  tests/api/test_reducer.py tests/api/test_runtime_events.py
```

- [ ] **Step 2: Trim `vocabularies.py`** to only:

```python
from enum import StrEnum, auto


class DevcontainerStatus(StrEnum):
    CREATED = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()
```

- [ ] **Step 3: Trim `tests/api/test_repositories.py`** to keep only devcontainer-repository tests (delete agent-session/inbox/approval/summary cases). If nothing devcontainer-specific remains, `git rm` it.

- [ ] **Step 4: Strip event intake from `runtime_channel.py`.** Replace the module so it contains only `AgentRegistry` (renamed conceptually to the per-devcontainer runtime registry) and the connection plumbing. Delete `persist_runtime_event`, `WORKER_SLOT`, `WorkerRegistry`, `ConnectionRegistry._slot_for`-for-worker, and the `reduce`/`project`/`invalidations_for` imports. The harness_status intake handler is added in Task 2.4. Minimal interim content:

```python
"""Per-devcontainer runtime WebSocket registry."""

from fastapi import WebSocket
from vibing_protocol import Command, CommandEnvelope


class RuntimeRegistry:
    """Keyed WebSocket slots, one per devcontainer_id."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    def is_connected(self, devcontainer_id: str) -> bool:
        return devcontainer_id in self._connections

    def register(self, devcontainer_id: str, websocket: WebSocket) -> bool:
        if devcontainer_id in self._connections:
            return False
        self._connections[devcontainer_id] = websocket
        return True

    def unregister(self, devcontainer_id: str, websocket: WebSocket) -> None:
        if self._connections.get(devcontainer_id) is websocket:
            del self._connections[devcontainer_id]

    async def send_command(self, devcontainer_id: str, command: Command) -> None:
        ws = self._connections.get(devcontainer_id)
        if ws is None:
            raise RuntimeError(f"No runtime connection for {devcontainer_id!r}")
        await ws.send_json(CommandEnvelope(command=command).model_dump())
```

- [ ] **Step 5: Note expected-red.** `main.py`, `runtime.py`, and `devcontainers.py` still import `WorkerRegistry`/`AgentRegistry`/`persist_runtime_event` and will fail to import until Tasks 2.2–2.4. Do not revert. Run only the green island:

Run: `uv run pytest -q tests/api/test_devcontainer_cli.py tests/api/test_database.py`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit -m "chore: delete event-sourcing layer (reducer, runtime_events, summaries, inbox/approval/session repos)"
```

---

### Task 1.6: Slim the schema to its surviving tables + add `harness_status`

**Files:**
- Modify: `src/vibing_api/core/schema.py`
- Modify: `tests/api/test_database.py` (assert new table set)

The DB is recreated locally (`vibing.db` is gitignored / disposable); no data migration needed. Drop all agent-session/event/inbox/approval tables; keep `app_meta` + `devcontainers`; add `harness_status`.

- [ ] **Step 1: Write the failing test** in `tests/api/test_database.py`:

```python
def test_schema_has_only_devcontainers_and_harness_status(tmp_path, monkeypatch):
    import sqlite3
    from vibing_api.core.schema import apply_schema

    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert tables == {"app_meta", "devcontainers", "harness_status"}
```

- [ ] **Step 2: Run it — expect FAIL** (old tables still present).

Run: `uv run pytest -q tests/api/test_database.py::test_schema_has_only_devcontainers_and_harness_status`

- [ ] **Step 3: Rewrite `schema.py`.** Bump `SCHEMA_VERSION = "5"`. Replace `_TABLE_STATEMENTS` with `app_meta`, `devcontainers` (unchanged), and:

```python
    """
    CREATE TABLE IF NOT EXISTS harness_status (
        devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        installed INTEGER NOT NULL,
        authenticated INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (devcontainer_id, name)
    )
    """,
```

Replace `_INDEX_STATEMENTS` with just `idx_harness_status_devcontainer ON harness_status(devcontainer_id)`. Delete `_migrate_schema`'s old ALTERs; keep only the `schema_version` upsert. Keep `_table_exists`/`_column_names` only if still referenced, else delete.

- [ ] **Step 4: Run it — expect PASS.**

Run: `uv run pytest -q tests/api/test_database.py`

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit -m "chore: slim sqlite schema to devcontainers + harness_status"
```

---

# Phase 2 — Rebuild backend devcontainer control

### Task 2.1: `DevcontainerService` — in-process lifecycle (direct CLI + direct status writes)

**Files:**
- Create: `src/vibing_api/core/devcontainer_service.py`
- Create: `tests/api/test_devcontainer_service.py`

**Interfaces:**
- Consumes: `DevcontainerCliAdapter` (`.start(local_path)`, `.stop(local_path)` → `DevcontainerSuccess|DevcontainerFailure`) from `vibing_api.core.devcontainer_cli`; `RuntimeInjector.inject(devcontainer_id, container_id, local_path)` from `vibing_api.core.runtime_injector` (the renamed `AgentLauncher.launch`); `DevcontainerRepository(conn).update(id, status=...)`; `Broadcaster.publish(SseEvent(scope="devcontainers", ids=[id]))`.
- Produces: `DevcontainerService(adapter, injector, broadcaster).start(devcontainer_id, local_path)` and `.stop(...)` — async coroutines that perform the full lifecycle and write status directly. A thin `run_in_background(coro)` wrapper (asyncio task) so routes return immediately.

- [ ] **Step 1: Rename `AgentLauncher.launch` → `RuntimeInjector.inject`** in `src/vibing_api/core/runtime_injector.py` (class `AgentLauncher` → `RuntimeInjector`, method `launch` → `inject`, drop "agent" wording in the docstring; keep the `docker cp` + `devcontainer exec` body). Update the injected command string to `vibing runtime devcontainer --control-plane-url ... --devcontainer-id ...` (unchanged shape).

- [ ] **Step 2: Write the failing test** `tests/api/test_devcontainer_service.py`:

```python
import asyncio
import pytest

from vibing_api.core.devcontainer_cli import DevcontainerSuccess, DevcontainerFailure
from vibing_api.core.devcontainer_service import DevcontainerService
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


class FakeInjector:
    def __init__(self):
        self.calls = []
    async def inject(self, devcontainer_id, container_id, local_path):
        self.calls.append((devcontainer_id, container_id, local_path))


class FakeRepo:
    def __init__(self):
        self.statuses = []
    def update(self, devcontainer_id, *, status):
        self.statuses.append((devcontainer_id, status))


class FakeBroadcaster:
    def __init__(self):
        self.events = []
    def publish(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_start_writes_starting_then_running_and_injects(monkeypatch):
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"}))
    injector = FakeInjector()
    repo = FakeRepo()
    bc = FakeBroadcaster()
    svc = DevcontainerService(adapter, injector, broadcaster=bc, repo_factory=lambda: repo)

    await svc.start("dc1", "/path")

    assert repo.statuses == [("dc1", DevcontainerStatus.STARTING), ("dc1", DevcontainerStatus.RUNNING)]
    assert injector.calls == [("dc1", "c1", "/path")]
    assert [e.scope for e in bc.events] == ["devcontainers", "devcontainers"]


@pytest.mark.asyncio
async def test_start_failure_writes_error_and_skips_injection():
    adapter = FakeAdapter(DevcontainerFailure(operation="start", command=[], exit_code=1, stderr_tail="boom", message="failed"))
    injector = FakeInjector()
    repo = FakeRepo()
    svc = DevcontainerService(adapter, injector, broadcaster=FakeBroadcaster(), repo_factory=lambda: repo)

    await svc.start("dc1", "/path")

    assert repo.statuses[-1] == ("dc1", DevcontainerStatus.ERROR)
    assert injector.calls == []
```

- [ ] **Step 3: Run it — expect FAIL** (`devcontainer_service` not found).

Run: `uv run pytest -q tests/api/test_devcontainer_service.py`

- [ ] **Step 4: Implement `devcontainer_service.py`.**

```python
"""In-process Devcontainer lifecycle (ADR-0014).

Replaces the Host Runtime Worker: the Control Plane shells out to the Dev Container CLI
directly, writes status to the read model as it progresses, and injects the Devcontainer
Runtime after a successful start. Long ops run in a background task; routes return 202.
"""

import asyncio
from collections.abc import Callable

from logzero import logger

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.database import get_connection
from vibing_api.core.devcontainer_cli import DevcontainerCliAdapter, DevcontainerFailure
from vibing_api.core.runtime_injector import RuntimeInjector
from vibing_api.core.vocabularies import DevcontainerStatus
from vibing_api.repositories.devcontainers import DevcontainerRepository


class DevcontainerService:
    def __init__(
        self,
        adapter: DevcontainerCliAdapter,
        injector: RuntimeInjector,
        *,
        broadcaster: Broadcaster | None = None,
        repo_factory: Callable[[], object] | None = None,
    ) -> None:
        self._adapter = adapter
        self._injector = injector
        self._broadcaster = broadcaster
        self._repo_factory = repo_factory

    def _set_status(self, devcontainer_id: str, status: DevcontainerStatus) -> None:
        if self._repo_factory is not None:
            self._repo_factory().update(devcontainer_id, status=status)  # test seam
        else:
            with get_connection() as conn:
                DevcontainerRepository(conn).update(devcontainer_id, status=status)
                conn.commit()
        if self._broadcaster is not None:
            self._broadcaster.publish(SseEvent(scope="devcontainers", ids=[devcontainer_id]))

    async def start(self, devcontainer_id: str, local_path: str) -> None:
        self._set_status(devcontainer_id, DevcontainerStatus.STARTING)
        result = await self._adapter.start(local_path)
        if isinstance(result, DevcontainerFailure):
            logger.error("devcontainer start failed (%s): %s", devcontainer_id, result.message)
            self._set_status(devcontainer_id, DevcontainerStatus.ERROR)
            return
        self._set_status(devcontainer_id, DevcontainerStatus.RUNNING)
        container_id = result.payload.get("container_id")
        if container_id:
            try:
                await self._injector.inject(devcontainer_id, container_id, local_path)
            except Exception:
                logger.warning("runtime injection failed for %s; ignoring", devcontainer_id)
        else:
            logger.warning("no container_id in up output for %s; skipping injection", devcontainer_id)

    async def stop(self, devcontainer_id: str, local_path: str) -> None:
        self._set_status(devcontainer_id, DevcontainerStatus.STOPPING)
        result = await self._adapter.stop(local_path)
        if isinstance(result, DevcontainerFailure):
            logger.error("devcontainer stop failed (%s): %s", devcontainer_id, result.message)
            self._set_status(devcontainer_id, DevcontainerStatus.ERROR)
            return
        self._set_status(devcontainer_id, DevcontainerStatus.STOPPED)


def run_in_background(coro) -> "asyncio.Task[None]":
    return asyncio.create_task(coro)
```

- [ ] **Step 5: Run it — expect PASS.** Add `asyncio_mode = "auto"` is already implied; if `pytest.mark.asyncio` is unavailable, check `tests/devcontainer_runtime` for the existing async pattern and match it. Run:

`uv run pytest -q tests/api/test_devcontainer_service.py`

- [ ] **Step 6: Commit.**

```bash
git add -A && git commit -m "feat(api): in-process DevcontainerService driving the Dev Container CLI directly"
```

---

### Task 2.2: Wire start/stop routes to the service (202 + background)

**Files:**
- Modify: `src/vibing_api/api/routes/devcontainers.py`
- Modify: `tests/api/test_devcontainer_lifecycle.py`

**Interfaces:**
- Consumes: `app.state.devcontainer_service: DevcontainerService` (set in Task 2.5), `app.state.runtime_manager: RuntimeRegistry`.
- Produces: `POST /devcontainers/{id}/start` and `/stop` → `202`, body is the current `Devcontainer`, status transitions happen in the background.

- [ ] **Step 1: Rewrite `_dispatch_lifecycle` + the `RuntimeConnection` view.** Remove `WORKER_SLOT`/`WorkerRegistry`/`Command`/`CommandType` imports. `RuntimeConnection` keeps only `runtime_connected` (rename from `agent_connected`; drop `worker_connected`). Lifecycle:

```python
from vibing_api.core.devcontainer_service import DevcontainerService, run_in_background
from vibing_api.core.runtime_channel import RuntimeRegistry

def _with_runtime(devcontainer, *, runtime_manager: RuntimeRegistry):
    runtime = RuntimeConnection(runtime_connected=runtime_manager.is_connected(devcontainer.id))
    return DevcontainerView(**devcontainer.model_dump(), runtime=runtime)

async def _dispatch_lifecycle(devcontainer_id, request, action, allowed_from):
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    if devcontainer.status not in allowed_from:
        raise InvalidDevcontainerStateError(action, devcontainer.status, allowed_from)
    service: DevcontainerService = request.app.state.devcontainer_service
    coro = service.start(devcontainer.id, devcontainer.local_path) if action == "start" \
        else service.stop(devcontainer.id, devcontainer.local_path)
    run_in_background(coro)
    return devcontainer
```

Update `start_devcontainer`/`stop_devcontainer` to call `_dispatch_lifecycle(devcontainer_id, request, "start"/"stop", _START_ALLOWED_FROM/_STOP_ALLOWED_FROM)` (drop the `CommandType` arg). Remove `RuntimeUnavailableError` usage (the in-process service is always available; CLI-missing surfaces as an `error` status later, not a pre-flight 503).

- [ ] **Step 2: Update list/get handlers** to use `_with_runtime(item, runtime_manager=request.app.state.runtime_manager)` and drop all `worker_connected` references.

- [ ] **Step 3: Update `tests/api/test_devcontainer_lifecycle.py`** to assert: start returns 202; after the background task runs, status is `running` (use a fake service or a fake adapter injected via `app.state.devcontainer_service`). Mirror the existing test's fixture style in `tests/api/conftest.py`. Replace assertions on emitted Commands with assertions on the service being invoked / status written.

- [ ] **Step 4: Run** `uv run pytest -q tests/api/test_devcontainer_lifecycle.py` — expect PASS (after Task 2.5 wiring; if run before, mark expected-red and proceed).

- [ ] **Step 5: Commit.**

```bash
git add -A && git commit -m "feat(api): devcontainer start/stop run the in-process service (202 + background)"
```

---

### Task 2.3: `harness_status` repository

**Files:**
- Create: `src/vibing_api/repositories/harness_status.py`
- Create: `tests/api/test_harness_status_repository.py`

**Interfaces:**
- Produces: `HarnessStatusRepository(conn)` with `upsert(devcontainer_id, name, installed, authenticated) -> None` and `list(devcontainer_id) -> list[HarnessStatusRow]` where `HarnessStatusRow` is a pydantic model `{name, installed, authenticated}`.

- [ ] **Step 1: Write the failing test:**

```python
import sqlite3
from vibing_api.core.schema import apply_schema
from vibing_api.repositories.harness_status import HarnessStatusRepository


def _conn():
    c = sqlite3.connect(":memory:")
    apply_schema(c)
    c.execute(
        "INSERT INTO devcontainers (id,name,local_path,status,created_at,updated_at) "
        "VALUES ('dc1','n','/p','running','t','t')"
    )
    return c


def test_upsert_then_list():
    conn = _conn()
    repo = HarnessStatusRepository(conn)
    repo.upsert("dc1", "codex", installed=True, authenticated=False)
    repo.upsert("dc1", "codex", installed=True, authenticated=True)  # overwrite
    repo.upsert("dc1", "cursor", installed=False, authenticated=False)
    rows = {r.name: r for r in repo.list("dc1")}
    assert rows["codex"].authenticated is True
    assert rows["cursor"].installed is False
```

- [ ] **Step 2: Run — expect FAIL.**

Run: `uv run pytest -q tests/api/test_harness_status_repository.py`

- [ ] **Step 3: Implement the repo** following the existing `repositories/devcontainers.py` style (constructor takes a `sqlite3.Connection`, SQL only, caller commits). Store booleans as `0/1`, stamp `updated_at` via the same timestamp helper the other repos use; expose a `HarnessStatusRow(BaseModel)`.

- [ ] **Step 4: Run — expect PASS.** **Step 5: Commit** `feat(api): harness_status repository`.

---

### Task 2.4: Harness-status intake on the runtime WS channel

**Files:**
- Modify: `src/vibing_api/core/runtime_channel.py` (add intake helper)
- Modify: `src/vibing_api/api/routes/runtime.py` (rewrite `_serve` + `agent_ws`; rename worker endpoint away)
- Modify: `tests/api/test_runtime_channel.py` (rewrite for harness_status), `tests/api/test_agent_channel.py` (rewrite/rename), `tests/api/test_runtime_connection_invalidations.py`
- Delete: `tests/api/test_runtime_status.py` if it only covered the worker slot; otherwise rewrite for `runtime_connected`.

**Interfaces:**
- Produces: `HarnessStatusItem`/`HarnessStatusEnvelope` in `vibing_protocol` (added here, additively — see Step 0); `persist_harness_status(devcontainer_id, items, broadcaster)` that upserts each row and publishes `SseEvent(scope="harnesses", ids=[devcontainer_id])`.

> **Ordering note (controller fix):** The harness wire types are needed by this task and by Task 3.2, both of which run before Task 4.1. So they are added **additively** here (Step 0) — leave all existing protocol types (`RuntimeEvent`, etc.) in place. Task 4.1 then becomes a pure deletion/slimming of the old types + final export cleanup.

- [ ] **Step 0: Add the harness wire types to `vibing_protocol` (additive).** In `src/vibing_protocol/messages.py` add:

```python
class HarnessStatusItem(BaseModel):
    name: str
    installed: bool
    authenticated: bool

class HarnessStatusEnvelope(BaseModel):
    type: Literal["harness_status"] = "harness_status"
    devcontainer_id: str
    items: list[HarnessStatusItem]
```

Export both from `src/vibing_protocol/__init__.py` (add to imports + `__all__`). Do NOT remove any existing exports. Verify `uv run python -c "from vibing_protocol import HarnessStatusEnvelope, HarnessStatusItem"`.

- [ ] **Step 1: Add `persist_harness_status` to `runtime_channel.py`:**

```python
from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.database import get_connection
from vibing_api.repositories.harness_status import HarnessStatusRepository


def persist_harness_status(devcontainer_id, items, broadcaster=None):
    with get_connection() as conn:
        repo = HarnessStatusRepository(conn)
        for item in items:
            repo.upsert(devcontainer_id, item.name, installed=item.installed, authenticated=item.authenticated)
        conn.commit()
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="harnesses", ids=[devcontainer_id]))
```

- [ ] **Step 2: Rewrite `routes/runtime.py`.** Single WS endpoint `/runtime/agent/ws` (keep the path for ADR-0004 continuity; the worker endpoint `/runtime/ws` and `get_runtime_status` are deleted). `_serve` registers by `devcontainer_id` then loops handling exactly two inbound types: `runtime_registered` and `harness_status` (validate with `HarnessStatusEnvelope`, call `persist_harness_status`). Remove the `runtime_event`/`transcript_response`/`turn_delta` branches. Keep the `_Reject` already-connected handling.

- [ ] **Step 3: Rewrite the channel tests** to: register a fake agent, send a `harness_status` envelope, assert rows upserted + a `harnesses` SSE invalidation published. Delete worker-slot assertions.

- [ ] **Step 4: Run** `uv run pytest -q tests/api/test_runtime_channel.py` — expect PASS.

- [ ] **Step 5: Commit** `feat(api): harness-status intake over the runtime channel; drop worker slot`.

---

### Task 2.5: App wiring (`main.py`) + harnesses route

**Files:**
- Modify: `src/vibing_api/main.py`
- Create: `src/vibing_api/api/routes/harnesses.py`, `src/vibing_api/api/schemas/harnesses.py`
- Create: `tests/api/test_harnesses_api.py`

**Interfaces (frontend contract — already consumed by `apps/web/src/lib/api/endpoints.ts`):**
- `GET /devcontainers/{id}/harnesses` → `{items:[{name,installed,authenticated}]}`
- `POST /devcontainers/{id}/harnesses/{name}/authenticate` → sends `authenticate_harness` Command to the runtime with the stored credential; returns `202`. (The fresh status arrives later via the `harnesses` SSE invalidation → refetch.)
- **Drop** `POST .../install` (ADR-0012: authenticate installs on demand) — remove it from the frontend in Task 5.1.

- [ ] **Step 1: `main.py`** — set `app.state.runtime_manager = RuntimeRegistry()`, build the `DevcontainerCliAdapter` + `RuntimeInjector` + `DevcontainerService(adapter, injector, broadcaster=app.state.broadcaster)` and store as `app.state.devcontainer_service`. Remove `AgentRegistry`/`WorkerRegistry`/`SessionStreamRegistry`. Router tuple: `health, status, config, devcontainers, harnesses, settings_route, diagnostics, runtime, events`.

- [ ] **Step 2: `schemas/harnesses.py`** — `HarnessStatusItem(name:str, installed:bool, authenticated:bool)` and `HarnessStatusList(items:list[HarnessStatusItem])`.

- [ ] **Step 3: Write failing test** `tests/api/test_harnesses_api.py`: seed a devcontainer + two harness_status rows, `GET /devcontainers/dc1/harnesses` returns them; `POST .../codex/authenticate` with a connected fake runtime returns 202 and the runtime received an `authenticate_harness` Command.

- [ ] **Step 4: Implement `routes/harnesses.py`.** GET reads `HarnessStatusRepository.list`. Authenticate loads the stored credential (Task 2.6 provides `CredentialStore`; until then read from a stub), checks `runtime_manager.is_connected(id)` (else `RuntimeUnavailableError`), and `await runtime_manager.send_command(id, Command(type=CommandType.AUTHENTICATE_HARNESS, devcontainer_id=id, payload={"harness":name, "credentials":blob}))`.

- [ ] **Step 5: Run** `uv run pytest -q tests/api/test_harnesses_api.py` — expect PASS. Then full backend suite `uv run pytest -q tests/api` — expect PASS. **Step 6: Commit** `feat(api): harnesses endpoints + app wiring for in-process control`.

---

### Task 2.6: Harness credential storage + capture (ADR-0012)

**Files:**
- Modify: `src/vibing_api/core/schema.py` (add `harness_credentials` table; bump to `"6"`), `tests/api/test_database.py`
- Create: `src/vibing_api/repositories/harness_credentials.py`, `tests/api/test_harness_credentials_repository.py`
- Create: route additions in `src/vibing_api/api/routes/harnesses.py` for credential CRUD (used by Settings page) + a `vibing harness capture` CLI command (Task 4/5).

**Interfaces:**
- `HarnessCredentialRepository.upsert(name, blob_json) / get(name) / list()` — `blob` stored as JSON text, plaintext (ADR-0012).
- `GET /settings/harness-credentials` → list of `{name, configured: bool}` (never return the secret); `PUT /settings/harness-credentials/{name}` with `{blob:{...}}`.

- [ ] **Step 1:** Add the `harness_credentials (name TEXT PRIMARY KEY, blob TEXT NOT NULL, updated_at TEXT NOT NULL)` table; update the `test_schema_has_only_*` test's expected set to `{"app_meta","devcontainers","harness_status","harness_credentials"}`.
- [ ] **Step 2:** TDD the repository (upsert/get/list), mirroring existing repo style.
- [ ] **Step 3:** TDD the settings routes (configured-flag only; never echo secrets).
- [ ] **Step 4:** Wire authenticate (Task 2.5 Step 4) to read the real blob via `HarnessCredentialRepository`.
- [ ] **Step 5:** Run `uv run pytest -q tests/api` — expect PASS. **Commit** `feat(api): harness credential storage + settings endpoints`.

---

# Phase 3 — Rebuild the Devcontainer Runtime

### Task 3.1: Make `runtime_client.py` self-contained

**Files:**
- Modify: `src/vibing_devcontainer_runtime/runtime_client.py` (the moved file)
- Modify: `tests/devcontainer_runtime/` — add `test_runtime_client.py` (port the kept cases from the deleted `tests/runtime_client/test_runtime_channel_client.py`)

- [ ] **Step 1:** Confirm `runtime_client.py` imports only `vibing_protocol` + stdlib/`websockets`. It already exposes `RuntimeChannelClient` with `on_request`, `send_envelope`, `run`/`run_blocking`. Keep `on_request`/transcript machinery **only if** still used — it is not (transcripts are gone), so delete `on_request`, `_request_handlers`, and the request/reply dispatch branch; keep command receive + `send_envelope`.
- [ ] **Step 2:** Port the reconnect/backoff/command-dispatch tests into `tests/devcontainer_runtime/test_runtime_client.py`; drop request/reply tests.
- [ ] **Step 3:** Run `uv run pytest -q tests/devcontainer_runtime/test_runtime_client.py` — expect PASS. **Commit** `refactor(runtime): fold runtime-client in, drop request/reply machinery`.

---

### Task 3.2: Slim the runtime command handler to harness-only

**Files:**
- Modify: `src/vibing_devcontainer_runtime/command_handler.py`
- Modify: `tests/devcontainer_runtime/test_command_handler_harness.py`

**Interfaces:**
- Produces: `HarnessCommandHandler(harness_manager)` with `handle(command, send)` that handles only `AUTHENTICATE_HARNESS`: authenticate, then `await send(HarnessStatusEnvelope(devcontainer_id=..., items=[...]))`.

- [ ] **Step 1: Rewrite `command_handler.py`** removing all `claude_runner`/`running_sessions`/`RuntimeEvent`/`TurnDelta` imports and every session method. New body:

```python
"""HarnessCommandHandler: authenticate_harness only; reports HarnessStatus back."""

from collections.abc import Awaitable, Callable

from logzero import logger
from pydantic import BaseModel
from vibing_protocol import Command, CommandType, HarnessStatusEnvelope, HarnessStatusItem

from vibing_devcontainer_runtime.harness_manager import HarnessManager

SendFn = Callable[[BaseModel], Awaitable[None]]


class HarnessCommandHandler:
    def __init__(self, harness_manager: HarnessManager, devcontainer_id: str) -> None:
        self._harness = harness_manager
        self._devcontainer_id = devcontainer_id

    async def handle(self, command: Command, send: SendFn) -> None:
        if command.type != CommandType.AUTHENTICATE_HARNESS:
            logger.info("Ignoring unsupported command: %s", command.type)
            return
        payload = command.payload or {}
        status = await self._harness.authenticate(payload.get("harness", ""), payload.get("credentials") or {})
        await send(self._envelope([status]))

    def _envelope(self, statuses) -> HarnessStatusEnvelope:
        return HarnessStatusEnvelope(
            devcontainer_id=self._devcontainer_id,
            items=[HarnessStatusItem(name=s.name, installed=s.installed, authenticated=s.authenticated) for s in statuses],
        )

    async def report_all(self, send: SendFn) -> None:
        await send(self._envelope(await self._harness.list_statuses()))
```

- [ ] **Step 2: Rewrite the harness command-handler test** to assert: an `AUTHENTICATE_HARNESS` command triggers `harness_manager.authenticate` and a `HarnessStatusEnvelope` is sent; `report_all` sends the full list.
- [ ] **Step 3:** Run `uv run pytest -q tests/devcontainer_runtime/test_command_handler_harness.py` — expect PASS. **Commit** `refactor(runtime): harness-only command handler that reports status`.

---

### Task 3.3: Rewrite the runtime CLI (report status on connect; no agent sessions)

**Files:**
- Modify: `src/vibing_devcontainer_runtime/cli.py`
- Modify: `tests/devcontainer_runtime/test_cli.py`

- [ ] **Step 1: Rewrite `cli.py`** removing `ClaudeCodeRunner`, `TranscriptReader`, `AgentCommandHandler`, `_make_emit`. Use `from vibing_devcontainer_runtime.runtime_client import RuntimeChannelClient` and `HarnessCommandHandler`. `RegisterEnvelope(devcontainer_id=...)` (no `source`). After connect, call `handler.report_all(client.send_envelope)` once registration completes — implement by passing an `on_connect` callback to the client, or by sending the first status report before `client.run()` returns control (simplest: a small `report_on_register` hook in `RuntimeChannelClient` invoked right after the `runtime_registered` send). Keep the MCP server + `DelegatedRunManager` wiring **unchanged** except `_make_emit` for delegated runs is removed (delegated runs are in-container only, ADR-0015 / Q9=A — `DelegatedRunManager` no longer emits upward; pass a no-op or drop the emit param).

- [ ] **Step 2:** Adjust `DelegatedRunManager` construction to not require an upward `emit` (it still tracks runs in-memory for MCP `get_status`/`get_result`). If its constructor requires `emit`, change it to optional / remove the emit calls (and update `tests/devcontainer_runtime/test_delegated_runs.py` to drop the emit assertions).

- [ ] **Step 3:** Update `test_cli.py` to assert the runtime serves the MCP server + connects the harness command channel and sends an initial `harness_status`. Run `uv run pytest -q tests/devcontainer_runtime` — expect PASS. **Commit** `refactor(runtime): cli is harness mgmt + MCP only; reports status on connect`.

---

# Phase 4 — Slim the protocol

### Task 4.1: Reduce `vibing_protocol` to the three surviving message kinds

> **Ordering note (controller fix):** `HarnessStatusItem`/`HarnessStatusEnvelope` were already added additively in Task 2.4 — do NOT re-add them. This task is now **deletion/slimming only**: remove the old types and do the final export cleanup.

**Files:**
- Modify: `src/vibing_protocol/commands.py`, `messages.py`, `__init__.py`
- Delete: `src/vibing_protocol/runtime_events.py`, `src/vibing_protocol/claude_output.py`
- Delete: `tests/protocol/test_claude_output.py`, `tests/protocol/test_transcript_messages.py`
- Modify/keep: `tests/protocol/test_harness_vocab.py`

- [ ] **Step 1:** `commands.py` — `CommandType` keeps only `AUTHENTICATE_HARNESS`. Keep `Command` (drop `agent_session_id` field; keep `devcontainer_id`, `payload`). Update any consumers of dropped command types (there should be none left after Phase 1–3; grep to confirm).
- [ ] **Step 2:** `messages.py` — keep `RegisterEnvelope` (fields: `type="runtime_registered"`, `devcontainer_id: str`), `CommandEnvelope`, and the `HarnessStatusItem`/`HarnessStatusEnvelope` added in Task 2.4. Delete `RuntimeEventEnvelope`, all transcript + turn-delta models. Also confirm `RegisterEnvelope` no longer carries the old `source`/`RuntimeEventSource` field (drop it if present, since the umbrella source enum is being removed).
- [ ] **Step 3:** `runtime_events.py` and `claude_output.py` deleted. `__init__.py` exports exactly: `COMMAND_TYPES, Command, CommandType, CommandEnvelope, RegisterEnvelope, HarnessStatusItem, HarnessStatusEnvelope`.
- [ ] **Step 4:** Grep for dangling imports of removed names across `src/` and `tests/`:

Run: `rg -n "RuntimeEvent|EventType|RuntimeEventSource|TurnDelta|Transcript|extract_claude_result_text" src tests`
Expected: no hits. Fix any that remain.

- [ ] **Step 5:** Run `uv run pytest -q tests/protocol && uv run mypy src` — expect PASS. **Commit** `refactor(protocol): slim to register + command + harness_status`.

---

# Phase 5 — Frontend reconciliation

### Task 5.1: Remove Delegated Runs UI; drop the install button; rename runtime flag

The frontend already renders harness status and talks to `/harnesses` (good). Reconcile to the agreed backend: no delegated-run tracking (Q9=A), no separate install endpoint (ADR-0012), `runtime_connected` not `worker_connected`/`agent_connected`.

**Files:**
- Delete: `src/components/DelegatedRuns.tsx`, `src/components/__tests__/DelegatedRuns.test.tsx`, `src/mock/state/delegatedRuns.ts`, `src/mock/__tests__/delegatedRuns.test.ts`
- Modify: `src/lib/api/endpoints.ts` (drop `fetchDelegatedRuns`, `stopDelegatedRun`, `installHarness`), `src/lib/api/types.ts` (drop `DelegatedRun*`; change `RuntimeConnection`/`RuntimeStatus` to `runtime_connected: boolean`)
- Modify: `src/routes/DevcontainerDetail.tsx` (remove the DelegatedRuns section + install action), `src/components/HarnessList.tsx` (remove install button), `src/mock/handlers.ts` + `src/mock/events.ts` (drop `delegated_runs` scope + handlers), `src/components/RailBackend.tsx` / any `worker_connected` reader.

- [ ] **Step 1:** Delete the files above (`git rm`).
- [ ] **Step 2:** Remove the delegated-run + install endpoints/types; update `RuntimeConnection` to `{ runtime_connected: boolean }` and fix all readers.
- [ ] **Step 3:** Remove the DelegatedRuns section from `DevcontainerDetail.tsx` and the install button from `HarnessList.tsx`; keep the per-harness status rows + Authenticate button.
- [ ] **Step 4:** Update mock handlers/events to drop the `delegated_runs` scope; keep `harnesses` scope.
- [ ] **Step 5:** Run `pnpm test && pnpm build` in `apps/web/` — expect PASS. **Commit** `refactor(web): drop delegated-runs UI + install action; runtime_connected flag`.

---

# Phase 6 — Docs & CLI surface

### Task 6.1: CLI surface cleanup

**Files:**
- Modify: `src/vibing_cli/__init__.py` (remove `runtime host`; keep `runtime devcontainer`), `src/vibing_cli/CLAUDE.md`
- Create: `src/vibing_cli/client/harnesses.py` (read harness status + trigger authenticate + manage credentials), wire as `vibing harness ...`
- Delete: `src/vibing_cli/client/devcontainers.py`'s nested `session` sub-app; `tests/cli/test_sessions.py`
- Modify: `tests/cli/test_devcontainers.py`

- [ ] **Step 1:** In `__init__.py` remove `from vibing_host_runtime.cli import ...` and the `runtime_app.add_typer(host_runtime_app, name="host")` line. Remove the `session` sub-app from `client/devcontainers.py`.
- [ ] **Step 2:** `git rm tests/cli/test_sessions.py`. Add `vibing harness` commands (`ls <devcontainer>`, `authenticate <devcontainer> <name>`, `creds set <name>`), thin HTTP glue mirroring `client/system.py`.
- [ ] **Step 3:** Run `uv run pytest -q tests/cli` — expect PASS. **Commit** `chore(cli): drop runtime host + session commands; add harness commands`.

---

### Task 6.2: Documentation sweep

**Files:**
- Modify: `docs/overview.md`, `docs/deployment.md`, `README.md`, `docs/foundation-api.md`
- Modify: `src/CLAUDE.md`, `src/vibing_api/CLAUDE.md`, `src/vibing_devcontainer_runtime/CLAUDE.md`, `src/vibing_protocol/CLAUDE.md`, `apps/web/CLAUDE.md`
- Delete: `src/vibing_host_runtime/CLAUDE.md`, `src/vibing_runtime_client/CLAUDE.md` (gone with their packages)
- Verify: `CONTEXT.md` + ADRs 0014/0015 already updated (this session).

- [ ] **Step 1:** Rewrite `docs/overview.md`: 4 packages, one lifecycle (Control Plane–owned), single runtime WS endpoint, harness workflow; remove Agent Session / Runtime Event / star-topology / host-worker sections and the obsolete MVP bullets.
- [ ] **Step 2:** Rewrite `docs/deployment.md`: no `vibing runtime host`; the backend injects the runtime; container contract = package manager + egress + MCP port (drop "authenticated `claude` required for sessions").
- [ ] **Step 3:** Update each `CLAUDE.md` to match the new file lists/responsibilities; delete the two for removed packages.
- [ ] **Step 4:** Update `README.md` run instructions (start the backend; the host worker step is gone).
- [ ] **Step 5:** Grep the docs for stale terms:

Run: `rg -ni "host runtime|host worker|agent session|runtime event|star topology|worker_connected" docs README.md src/**/CLAUDE.md`
Expected: only ADR history (0002/0003/0008–0010, marked SUPERSEDED) and ADR-0014/0015 narrative may mention them. Fix the rest.

- [ ] **Step 6:** **Commit** `docs: align overview/deployment/readme/claude.md with collapsed-runtime architecture`.

---

### Task 6.3: Final full-suite verification

- [ ] **Step 1:** `uv run ruff check src tests`
- [ ] **Step 2:** `uv run ruff format --check src tests`
- [ ] **Step 3:** `uv run mypy src`
- [ ] **Step 4:** `uv run pytest -q`
- [ ] **Step 5:** `cd apps/web && pnpm test && pnpm build`
- [ ] **Step 6:** `rg -n "vibing_host_runtime|vibing_runtime_client|agent_session|runtime_event" src tests apps/web/src` — expect no hits.
- [ ] **Step 7:** **Commit** any final fixups; the branch is ready for review/merge.

---

## Self-Review

**Spec coverage** (against the grilling decisions):
- Host worker → in-process: Tasks 1.4, 2.1, 2.2, 2.5. ✓
- Drop event log / direct mutation: Tasks 1.5, 1.6, 2.1, 2.4. ✓
- Agent WS stays (runtime only): Tasks 1.2, 2.4. ✓
- 202 + background: Task 2.1, 2.2. ✓
- Packages 6→4: Tasks 1.4, 3.1, 4.1. ✓
- Commands kept for runtime, agent-session ops dropped: Tasks 3.2, 4.1. ✓
- Drop agent-session subsystem: Tasks 1.2, 1.3, 1.5, 1.6. ✓
- Devcontainer Runtime = harness companion + MCP: Tasks 3.2, 3.3. ✓
- Delegated runs in-container only (A): Tasks 3.3, 5.1. ✓
- Harness status reported up + shown (B): Tasks 2.3, 2.4, 2.5, 3.2, 5.1. ✓
- Credentials on-demand (B, ADR-0012): Tasks 2.5, 2.6. ✓
- Wire protocol = register/command/harness_status: Task 4.1. ✓
- Naming retired (Agent Session, Host Runtime Worker, "agent"): Tasks 4.1, 6.2; CONTEXT.md done this session. ✓

**Known interface consistency points to honor during execution:**
- `HarnessStatusItem`/`HarnessStatusEnvelope` defined in `vibing_protocol` (Task 4.1) are imported by the runtime (3.2) and the backend intake (2.4) — same names, same fields `{name, installed, authenticated}`.
- `RuntimeRegistry.send_command(devcontainer_id, command)` signature (Task 1.5) is what the harnesses route calls (Task 2.5).
- `RuntimeConnection.runtime_connected` (backend Task 2.2) ↔ `types.ts` `runtime_connected` (Task 5.1).
- `DevcontainerService(adapter, injector, broadcaster=...)` constructor (Task 2.1) ↔ `main.py` wiring (Task 2.5).

**Ordering caveat (stated, not a defect):** Phase 1 leaves the devcontainer start/stop path and the `vibing_devcontainer_runtime` package import temporarily broken; Phases 2–3 restore them. Under subagent-driven execution, run the named green-island test commands per task rather than the full suite until Task 6.3.
