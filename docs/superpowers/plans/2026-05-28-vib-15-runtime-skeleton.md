# VIB-15 — Host and workspace runtime skeleton implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate `packages/protocol` as the canonical home for `Command` and `RuntimeEvent` shapes, refactor `vibing_api.core` to import from it, add no-op `HostRuntime` and `WorkspaceRuntime` skeletons in their respective packages with one unit test each, and write `docs/runtime-boundaries.md`.

**Architecture:** Two bare `uv init` placeholders (`packages/protocol`, `packages/workspace_runtime`) become src-layout libraries. `apps/api` and `packages/workspace_runtime` both depend on `vibing-protocol` via `tool.uv.sources` path dependencies (no root uv workspace). Behaviour everywhere stays fake/no-op — no Docker, Podman, Dev Container CLI, Claude Code, PTY, or background workers.

**Tech Stack:** Python 3.13, pydantic 2, uv (uv_build), pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-05-28-vib-15-runtime-skeleton-design.md`.

---

## File structure

**Create:**
- `packages/protocol/src/vibing_protocol/__init__.py`
- `packages/protocol/src/vibing_protocol/commands.py`
- `packages/protocol/src/vibing_protocol/runtime_events.py`
- `apps/api/src/vibing_api/host_runtime/__init__.py`
- `apps/api/tests/test_host_runtime.py`
- `packages/workspace_runtime/src/vibing_workspace_runtime/__init__.py`
- `packages/workspace_runtime/tests/__init__.py`
- `packages/workspace_runtime/tests/test_workspace_runtime.py`
- `docs/runtime-boundaries.md`

**Modify:**
- `packages/protocol/pyproject.toml` (replace contents)
- `packages/protocol/README.md` (replace one-line placeholder)
- `packages/workspace_runtime/pyproject.toml` (replace contents)
- `packages/workspace_runtime/README.md` (replace one-line placeholder)
- `apps/api/pyproject.toml` (add `vibing-protocol` dep + `[tool.uv.sources]`)
- `apps/api/src/vibing_api/core/commands.py` (replace with re-export shim)
- `apps/api/src/vibing_api/core/runtime_events.py` (import shapes from protocol; keep persistence)

**Generated (do not hand-edit):**
- `packages/protocol/uv.lock` (new)
- `packages/workspace_runtime/uv.lock` (regenerated)
- `apps/api/uv.lock` (regenerated)

**Delete:**
- `packages/protocol/main.py`
- `packages/workspace_runtime/main.py`

**Do NOT touch (must still compile + behave the same):**
- `apps/api/src/vibing_api/core/database.py`, `schema.py`, `config.py`, `errors.py`
- `apps/api/src/vibing_api/api/**` (HTTP routes)
- `apps/api/src/vibing_api/cli/**`, `dev/**`, `main.py`
- `apps/api/tests/test_runtime_events.py` (must keep passing unchanged)
- `apps/web/**`
- `docs/domain-model.md`

---

## Task 1: Stand up `vibing_protocol` package skeleton

**Files:**
- Delete: `packages/protocol/main.py`
- Create: `packages/protocol/src/vibing_protocol/__init__.py` (empty for now)
- Modify: `packages/protocol/pyproject.toml`
- Modify: `packages/protocol/README.md`

- [ ] **Step 1: Delete the `uv init` placeholder**

```bash
rm packages/protocol/main.py
```

- [ ] **Step 2: Create the src-layout directory + empty `__init__.py`**

```bash
mkdir -p packages/protocol/src/vibing_protocol
```

Then create `packages/protocol/src/vibing_protocol/__init__.py` with this exact (empty docstring-only) content:

```python
"""Shared control-plane message shapes for Vibing host and workspace runtimes."""
```

The full re-export list comes in Task 4 once the submodules exist.

- [ ] **Step 3: Replace `packages/protocol/pyproject.toml`**

```toml
[project]
name = "vibing-protocol"
version = "0.1.0"
description = "Shared control-plane message shapes for Vibing host and workspace runtimes."
readme = "README.md"
requires-python = ">=3.13"
dependencies = ["pydantic>=2.0"]

[build-system]
requires = ["uv_build>=0.11.16,<0.12.0"]
build-backend = "uv_build"

[tool.ruff]
line-length = 100
target-version = "py313"
```

- [ ] **Step 4: Replace `packages/protocol/README.md`**

```markdown
# vibing-protocol

Shared control-plane message shapes for the Vibing MVP runtimes.

This package defines the `Command` and `RuntimeEvent` data models plus their
vocabulary literals (`CommandType`, `EventType`, `RuntimeEventSource`). It has
no behaviour: dispatch, persistence, and transport live in consumers
(`apps/api`, `packages/workspace_runtime`).
```

- [ ] **Step 5: Sync the package**

Run from `packages/protocol/`:

```bash
uv sync
```

Expected: uv resolves `pydantic`, creates `.venv/`, writes `uv.lock`. No errors.

- [ ] **Step 6: Verify the package is importable**

Run from `packages/protocol/`:

```bash
uv run python -c "import vibing_protocol; print(vibing_protocol.__doc__)"
```

Expected output: `Shared control-plane message shapes for Vibing host and workspace runtimes.`

- [ ] **Step 7: Commit**

```bash
git add packages/protocol
git rm packages/protocol/main.py 2>/dev/null || true
git commit -m "$(cat <<'EOF'
VIB-15 Stand up vibing_protocol package skeleton

Convert packages/protocol from the bare uv init placeholder into a
src-layout library named vibing-protocol. No public API yet; the
shapes and vocab come in follow-up commits.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

`git rm` may already have happened during `git add` (since the file was deleted on disk and is staged for deletion); the `|| true` keeps the command idempotent.

---

## Task 2: Add `vibing_protocol.commands`

**Files:**
- Create: `packages/protocol/src/vibing_protocol/commands.py`

No unit tests for `commands.py` directly — the backend's `test_runtime_events.py` exercises `Command`/vocab through `record_runtime_event` once Task 7 lands. The protocol package stays test-free; coverage comes through consumers.

- [ ] **Step 1: Create `packages/protocol/src/vibing_protocol/commands.py`**

```python
"""Control-plane command vocabulary and message shape.

A Command represents user intent or a control-plane request directed at a
runtime (host or workspace). This module defines the allowed command types
and the typed message shape. Dispatch and execution live in consumers.
"""

from typing import Any, Literal, get_args

from pydantic import BaseModel

CommandType = Literal[
    "start_workspace",
    "stop_workspace",
    "restart_workspace",
    "start_claude_session",
    "stop_claude_session",
    "send_user_input",
    "resolve_approval",
]

COMMAND_TYPES: frozenset[str] = frozenset(get_args(CommandType))


class Command(BaseModel):
    """Control-plane request directed at a runtime."""

    type: CommandType
    workspace_id: str | None = None
    agent_session_id: str | None = None
    payload: dict[str, Any] | None = None
```

- [ ] **Step 2: Verify the module imports + the model constructs**

Run from `packages/protocol/`:

```bash
uv run python -c "from vibing_protocol.commands import COMMAND_TYPES, Command, CommandType; c = Command(type='start_workspace', workspace_id='ws1'); print(sorted(COMMAND_TYPES)); print(c.model_dump())"
```

Expected output (order of COMMAND_TYPES doesn't matter; the printed list will be sorted alphabetically):

```
['resolve_approval', 'restart_workspace', 'send_user_input', 'start_claude_session', 'start_workspace', 'stop_claude_session', 'stop_workspace']
{'type': 'start_workspace', 'workspace_id': 'ws1', 'agent_session_id': None, 'payload': None}
```

- [ ] **Step 3: Commit**

```bash
git add packages/protocol/src/vibing_protocol/commands.py
git commit -m "$(cat <<'EOF'
VIB-15 Add Command vocabulary and message shape to vibing_protocol

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add `vibing_protocol.runtime_events`

**Files:**
- Create: `packages/protocol/src/vibing_protocol/runtime_events.py`

- [ ] **Step 1: Create `packages/protocol/src/vibing_protocol/runtime_events.py`**

```python
"""Runtime-event vocabulary and message shape.

A RuntimeEvent is a structured event emitted by a runtime (host or workspace)
to the control plane. This module defines the allowed event types, the source
literal, and the typed message shape. Persistence lives in consumers.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field

EventType = Literal[
    "workspace_started",
    "workspace_failed",
    "claude_session_started",
    "claude_asked_question",
    "approval_requested",
    "approval_resolved",
    "session_completed",
    "session_failed",
]

RuntimeEventSource = Literal[
    "host_runtime_worker",
    "workspace_runtime_agent",
]

EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))
RUNTIME_EVENT_SOURCES: frozenset[str] = frozenset(get_args(RuntimeEventSource))


class InvalidRuntimeEventError(ValueError):
    """Raised when an event_type or source is not in the allowed vocabulary."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeEvent(BaseModel):
    """Structured event emitted by a runtime to the control plane."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str | None = None
    agent_session_id: str | None = None
    event_type: EventType
    source: RuntimeEventSource
    payload: dict[str, Any] | None = None
    created_at: str = Field(default_factory=_now_iso)
```

- [ ] **Step 2: Verify imports + the model constructs with defaults**

Run from `packages/protocol/`:

```bash
uv run python -c "from vibing_protocol.runtime_events import EVENT_TYPES, RUNTIME_EVENT_SOURCES, RuntimeEvent, InvalidRuntimeEventError; e = RuntimeEvent(event_type='workspace_started', source='host_runtime_worker', workspace_id='ws1'); print(len(e.id) > 0, len(e.created_at) > 0); print(sorted(RUNTIME_EVENT_SOURCES))"
```

Expected output:

```
True True
['host_runtime_worker', 'workspace_runtime_agent']
```

- [ ] **Step 3: Commit**

```bash
git add packages/protocol/src/vibing_protocol/runtime_events.py
git commit -m "$(cat <<'EOF'
VIB-15 Add RuntimeEvent vocabulary and message shape to vibing_protocol

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire `vibing_protocol.__init__.py` public re-exports

**Files:**
- Modify: `packages/protocol/src/vibing_protocol/__init__.py`

- [ ] **Step 1: Replace `packages/protocol/src/vibing_protocol/__init__.py`**

```python
"""Shared control-plane message shapes for Vibing host and workspace runtimes."""

from .commands import COMMAND_TYPES, Command, CommandType
from .runtime_events import (
    EVENT_TYPES,
    EventType,
    InvalidRuntimeEventError,
    RUNTIME_EVENT_SOURCES,
    RuntimeEvent,
    RuntimeEventSource,
)

__all__ = [
    "COMMAND_TYPES",
    "Command",
    "CommandType",
    "EVENT_TYPES",
    "EventType",
    "InvalidRuntimeEventError",
    "RUNTIME_EVENT_SOURCES",
    "RuntimeEvent",
    "RuntimeEventSource",
]
```

- [ ] **Step 2: Verify the public API resolves**

Run from `packages/protocol/`:

```bash
uv run python -c "from vibing_protocol import Command, RuntimeEvent, CommandType, EventType, RuntimeEventSource, COMMAND_TYPES, EVENT_TYPES, RUNTIME_EVENT_SOURCES, InvalidRuntimeEventError; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Lint check**

Run from `packages/protocol/`:

```bash
uv run --with ruff ruff check .
```

Expected output: `All checks passed!` (no errors).

`uv run --with ruff` pulls ruff transiently — `vibing-protocol` itself has no dev deps. If you prefer, run `ruff check .` from a venv that already has ruff (e.g. `cd ../../apps/api && uv run ruff check ../../packages/protocol`).

- [ ] **Step 4: Commit**

```bash
git add packages/protocol/src/vibing_protocol/__init__.py packages/protocol/uv.lock
git commit -m "$(cat <<'EOF'
VIB-15 Wire vibing_protocol public re-exports

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

`uv.lock` will have been created during Task 1's `uv sync`; if it was already committed there, the `add` is a no-op for it.

---

## Task 5: Wire `vibing-protocol` into `apps/api` as a path dependency

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/uv.lock` (via `uv lock`)

- [ ] **Step 1: Update `apps/api/pyproject.toml`**

Add `"vibing-protocol"` to the `dependencies` list and add a `[tool.uv.sources]` section. The full updated file:

```toml
[project]
name = "vibing-api"
version = "0.1.0"
description = "Vibing FastAPI backend"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.136.3",
    "pydantic-settings>=2.14.1",
    "rich>=15.0.0",
    "typer>=0.26.2",
    "uvicorn[standard]>=0.48.0",
    "vibing-protocol",
]

[dependency-groups]
dev = [
    "httpx>=0.28.1",
    "mypy>=2.1.0",
    "pytest>=9.0.3",
    "ruff>=0.15.14",
]

[project.scripts]
vibing = "vibing_api.cli:app"

[tool.uv.sources]
vibing-protocol = { path = "../../packages/protocol", editable = true }

[build-system]
requires = ["uv_build>=0.11.16,<0.12.0"]
build-backend = "uv_build"

[tool.ruff]
line-length = 100
target-version = "py313"
```

- [ ] **Step 2: Lock + sync**

Run from `apps/api/`:

```bash
uv lock
uv sync
```

Expected: uv resolves the editable path source, updates `uv.lock`, installs `vibing-protocol` into the apps/api venv in editable mode. No errors.

- [ ] **Step 3: Verify the backend can import protocol**

Run from `apps/api/`:

```bash
uv run python -c "from vibing_protocol import Command, RuntimeEvent; print('ok')"
```

Expected output: `ok`

- [ ] **Step 4: Run existing tests to confirm nothing regressed**

Run from `apps/api/`:

```bash
uv run pytest
```

Expected: all existing tests pass (including the 5 `test_runtime_events.py` tests). The backend hasn't changed yet, only its dependency graph has.

- [ ] **Step 5: Commit**

```bash
git add apps/api/pyproject.toml apps/api/uv.lock
git commit -m "$(cat <<'EOF'
VIB-15 Add vibing-protocol as a path dependency of apps/api

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Re-export Command vocab from `vibing_api.core.commands`

**Files:**
- Modify: `apps/api/src/vibing_api/core/commands.py`

- [ ] **Step 1: Replace `apps/api/src/vibing_api/core/commands.py`**

```python
"""Backwards-compatible re-exports for command vocabulary.

The canonical home is vibing_protocol.commands. This shim keeps existing
imports (e.g. `from vibing_api.core.commands import COMMAND_TYPES`) working.
"""

from vibing_protocol.commands import COMMAND_TYPES, Command, CommandType

__all__ = ["COMMAND_TYPES", "Command", "CommandType"]
```

- [ ] **Step 2: Verify nothing regressed**

Run from `apps/api/`:

```bash
uv run pytest
```

Expected: all tests still pass. The two callers of `COMMAND_TYPES` (`vibing_api.core.commands` and `apps/api/tests/test_runtime_events.py` — the latter imports it but does not assert on it) keep resolving.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/vibing_api/core/commands.py
git commit -m "$(cat <<'EOF'
VIB-15 Re-export Command vocab from vibing_protocol via vibing_api.core.commands

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Refactor `vibing_api.core.runtime_events` to use protocol shapes

**Files:**
- Modify: `apps/api/src/vibing_api/core/runtime_events.py`

This is the largest refactor in the plan. The persistence functions stay; the vocab + model definitions move out to protocol.

- [ ] **Step 1: Replace `apps/api/src/vibing_api/core/runtime_events.py`**

```python
"""Runtime-event persistence over the runtime_events SQLite table.

Vocabulary and message shape live in vibing_protocol. This module owns
only the read/write helpers.
"""

import json
import sqlite3
from typing import Any

from vibing_protocol.runtime_events import (
    EVENT_TYPES,
    EventType,
    InvalidRuntimeEventError,
    RUNTIME_EVENT_SOURCES,
    RuntimeEvent,
    RuntimeEventSource,
)

__all__ = [
    "EVENT_TYPES",
    "EventType",
    "InvalidRuntimeEventError",
    "RUNTIME_EVENT_SOURCES",
    "RuntimeEvent",
    "RuntimeEventSource",
    "list_runtime_events_by_session",
    "list_runtime_events_by_workspace",
    "record_runtime_event",
]


def record_runtime_event(
    conn: sqlite3.Connection,
    *,
    event_type: EventType,
    source: RuntimeEventSource,
    workspace_id: str | None = None,
    agent_session_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RuntimeEvent:
    """Validate, build, insert, return. Caller is responsible for commit."""
    if event_type not in EVENT_TYPES:
        raise InvalidRuntimeEventError(f"Unknown event_type: {event_type!r}")
    if source not in RUNTIME_EVENT_SOURCES:
        raise InvalidRuntimeEventError(f"Unknown source: {source!r}")

    event = RuntimeEvent(
        event_type=event_type,
        source=source,
        workspace_id=workspace_id,
        agent_session_id=agent_session_id,
        payload=payload,
    )
    payload_json = json.dumps(event.payload) if event.payload is not None else None
    conn.execute(
        "INSERT INTO runtime_events "
        "(id, workspace_id, agent_session_id, event_type, source, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            event.id,
            event.workspace_id,
            event.agent_session_id,
            event.event_type,
            event.source,
            payload_json,
            event.created_at,
        ),
    )
    return event


def _row_to_event(row: sqlite3.Row) -> RuntimeEvent:
    raw_payload = row["payload"]
    return RuntimeEvent(
        id=row["id"],
        workspace_id=row["workspace_id"],
        agent_session_id=row["agent_session_id"],
        event_type=row["event_type"],
        source=row["source"],
        payload=json.loads(raw_payload) if raw_payload is not None else None,
        created_at=row["created_at"],
    )


def list_runtime_events_by_workspace(
    conn: sqlite3.Connection, workspace_id: str
) -> list[RuntimeEvent]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, workspace_id, agent_session_id, event_type, source, payload, created_at "
        "FROM runtime_events WHERE workspace_id = ? ORDER BY created_at, id",
        (workspace_id,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]


def list_runtime_events_by_session(
    conn: sqlite3.Connection, agent_session_id: str
) -> list[RuntimeEvent]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, workspace_id, agent_session_id, event_type, source, payload, created_at "
        "FROM runtime_events WHERE agent_session_id = ? ORDER BY created_at, id",
        (agent_session_id,),
    ).fetchall()
    return [_row_to_event(row) for row in rows]
```

Key differences from the prior file:

- `EventType`, `RuntimeEventSource`, `EVENT_TYPES`, `RUNTIME_EVENT_SOURCES`, `RuntimeEvent`, `InvalidRuntimeEventError` come from `vibing_protocol.runtime_events` instead of being defined locally.
- `record_runtime_event` no longer generates `event_id` / `created_at` locally — it builds the `RuntimeEvent` first and uses its (default-populated) `id` and `created_at` to insert.
- The local `_now()` helper is removed.

- [ ] **Step 2: Run the existing test suite**

Run from `apps/api/`:

```bash
uv run pytest tests/test_runtime_events.py -v
```

Expected: all 6 tests pass (`test_record_runtime_event_persists_row`, `test_record_runtime_event_round_trips_payload`, `test_record_runtime_event_rejects_unknown_event_type`, `test_record_runtime_event_rejects_unknown_source`, `test_list_runtime_events_by_workspace_filters_and_orders`, `test_list_runtime_events_by_session_filters_and_orders`).

- [ ] **Step 3: Run the full suite as a sanity check**

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 4: Lint**

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/vibing_api/core/runtime_events.py
git commit -m "$(cat <<'EOF'
VIB-15 Use vibing_protocol shapes in vibing_api.core.runtime_events

Move EventType, RuntimeEventSource, RuntimeEvent and friends to
vibing_protocol; vibing_api.core.runtime_events now owns only the
SQLite read/write helpers and re-exports the protocol names so
existing import paths keep working.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: TDD the host runtime skeleton

**Files:**
- Create: `apps/api/tests/test_host_runtime.py` (write first)
- Create: `apps/api/src/vibing_api/host_runtime/__init__.py`

- [ ] **Step 1: Write the failing test — `apps/api/tests/test_host_runtime.py`**

```python
from vibing_api.host_runtime import HOST_COMMAND_TYPES, HostRuntime, NoopHostRuntime
from vibing_protocol import Command


def test_noop_host_runtime_handles_start_workspace() -> None:
    runtime: HostRuntime = NoopHostRuntime()
    events = runtime.handle(Command(type="start_workspace", workspace_id="ws1"))

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "workspace_started"
    assert event.source == "host_runtime_worker"
    assert event.workspace_id == "ws1"
    assert event.agent_session_id is None
    assert event.id
    assert event.created_at


def test_noop_host_runtime_returns_empty_for_unmapped_command() -> None:
    runtime = NoopHostRuntime()
    events = runtime.handle(Command(type="stop_workspace", workspace_id="ws1"))
    assert events == []


def test_host_command_types_cover_workspace_lifecycle() -> None:
    assert HOST_COMMAND_TYPES == {"start_workspace", "stop_workspace", "restart_workspace"}
```

- [ ] **Step 2: Run the test, verify it fails**

Run from `apps/api/`:

```bash
uv run pytest tests/test_host_runtime.py -v
```

Expected: failure on collection with `ModuleNotFoundError: No module named 'vibing_api.host_runtime'` (or an equivalent ImportError).

- [ ] **Step 3: Create `apps/api/src/vibing_api/host_runtime/__init__.py`**

```python
"""Host-side runtime skeleton.

The Host Runtime Worker owns workspace-lifecycle operations (eventually:
Dev Container CLI, Docker/Podman). This module only defines the interface
and a no-op implementation. No Docker, Podman, or Dev Container CLI calls.
"""

from typing import Protocol

from vibing_protocol import Command, EventType, RuntimeEvent

__all__ = ["HOST_COMMAND_TYPES", "HostRuntime", "NoopHostRuntime"]


HOST_COMMAND_TYPES: frozenset[str] = frozenset(
    {
        "start_workspace",
        "stop_workspace",
        "restart_workspace",
    }
)


class HostRuntime(Protocol):
    """Receive a host-side command, emit zero or more runtime events."""

    def handle(self, command: Command) -> list[RuntimeEvent]: ...


class NoopHostRuntime:
    """No-op host runtime. Does not call Docker, Podman, or Dev Container CLI."""

    _COMMAND_TO_EVENT: dict[str, EventType] = {
        "start_workspace": "workspace_started",
    }

    def handle(self, command: Command) -> list[RuntimeEvent]:
        event_type = self._COMMAND_TO_EVENT.get(command.type)
        if event_type is None:
            return []
        return [
            RuntimeEvent(
                event_type=event_type,
                source="host_runtime_worker",
                workspace_id=command.workspace_id,
            )
        ]
```

- [ ] **Step 4: Run the test, verify it passes**

```bash
uv run pytest tests/test_host_runtime.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Run the full backend suite**

```bash
uv run pytest
```

Expected: every test passes (existing + the 3 new ones).

- [ ] **Step 6: Lint**

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/vibing_api/host_runtime apps/api/tests/test_host_runtime.py
git commit -m "$(cat <<'EOF'
VIB-15 Add no-op HostRuntime skeleton in vibing_api.host_runtime

Defines HOST_COMMAND_TYPES, the HostRuntime Protocol, and a
NoopHostRuntime that maps start_workspace to a workspace_started
runtime event without invoking any container infrastructure.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Stand up `vibing_workspace_runtime` package skeleton

**Files:**
- Delete: `packages/workspace_runtime/main.py`
- Create: `packages/workspace_runtime/src/vibing_workspace_runtime/__init__.py` (empty placeholder)
- Create: `packages/workspace_runtime/tests/__init__.py`
- Modify: `packages/workspace_runtime/pyproject.toml`
- Modify: `packages/workspace_runtime/README.md`

- [ ] **Step 1: Delete the `uv init` placeholder**

```bash
rm packages/workspace_runtime/main.py
```

- [ ] **Step 2: Create the src + tests directories**

```bash
mkdir -p packages/workspace_runtime/src/vibing_workspace_runtime
mkdir -p packages/workspace_runtime/tests
```

- [ ] **Step 3: Create `packages/workspace_runtime/src/vibing_workspace_runtime/__init__.py` (placeholder)**

```python
"""Workspace-side runtime skeleton for the Vibing MVP."""
```

The full implementation lands in Task 10 (TDD).

- [ ] **Step 4: Create `packages/workspace_runtime/tests/__init__.py` (empty file)**

```python
```

Empty file. Mirrors `apps/api/tests/__init__.py`.

- [ ] **Step 5: Replace `packages/workspace_runtime/pyproject.toml`**

```toml
[project]
name = "vibing-workspace-runtime"
version = "0.1.0"
description = "Workspace-side runtime skeleton for the Vibing MVP."
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.0",
    "vibing-protocol",
]

[dependency-groups]
dev = ["pytest>=9.0.3", "ruff>=0.15.14"]

[tool.uv.sources]
vibing-protocol = { path = "../protocol", editable = true }

[build-system]
requires = ["uv_build>=0.11.16,<0.12.0"]
build-backend = "uv_build"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 6: Replace `packages/workspace_runtime/README.md`**

```markdown
# vibing-workspace-runtime

Workspace-side runtime skeleton for the Vibing MVP.

The Workspace Runtime Agent owns Claude-session lifecycle inside a workspace
(eventually: launching Claude Code, PTY, streaming output, approval
detection). This package currently ships a no-op `WorkspaceRuntime`
implementation — see `docs/runtime-boundaries.md` at the repo root for the
host-vs-workspace responsibility split.
```

- [ ] **Step 7: Sync the package**

Run from `packages/workspace_runtime/`:

```bash
uv sync
```

Expected: uv resolves pydantic, pytest, ruff, and the editable path source for `vibing-protocol`; creates `.venv/`; writes `uv.lock`. No errors.

- [ ] **Step 8: Verify the package imports**

Run from `packages/workspace_runtime/`:

```bash
uv run python -c "import vibing_workspace_runtime; from vibing_protocol import Command; print('ok')"
```

Expected output: `ok`

- [ ] **Step 9: Commit**

```bash
git add packages/workspace_runtime
git rm packages/workspace_runtime/main.py 2>/dev/null || true
git commit -m "$(cat <<'EOF'
VIB-15 Stand up vibing_workspace_runtime package skeleton

Convert packages/workspace_runtime from the bare uv init placeholder
into a src-layout library named vibing-workspace-runtime. Depends on
vibing-protocol via a path source. No public API yet; the runtime
implementation lands in the next commit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: TDD the workspace runtime skeleton

**Files:**
- Create: `packages/workspace_runtime/tests/test_workspace_runtime.py` (write first)
- Modify: `packages/workspace_runtime/src/vibing_workspace_runtime/__init__.py`

- [ ] **Step 1: Write the failing test — `packages/workspace_runtime/tests/test_workspace_runtime.py`**

```python
from vibing_protocol import Command
from vibing_workspace_runtime import (
    WORKSPACE_COMMAND_TYPES,
    NoopWorkspaceRuntime,
    WorkspaceRuntime,
)


def test_noop_workspace_runtime_handles_start_claude_session() -> None:
    runtime: WorkspaceRuntime = NoopWorkspaceRuntime()
    events = runtime.handle(
        Command(type="start_claude_session", workspace_id="ws1", agent_session_id="s1")
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "claude_session_started"
    assert event.source == "workspace_runtime_agent"
    assert event.workspace_id == "ws1"
    assert event.agent_session_id == "s1"
    assert event.id
    assert event.created_at


def test_noop_workspace_runtime_returns_empty_for_unmapped_command() -> None:
    runtime = NoopWorkspaceRuntime()
    events = runtime.handle(
        Command(type="send_user_input", workspace_id="ws1", agent_session_id="s1")
    )
    assert events == []


def test_workspace_command_types_cover_session_surface() -> None:
    assert WORKSPACE_COMMAND_TYPES == {
        "start_claude_session",
        "stop_claude_session",
        "send_user_input",
        "resolve_approval",
    }
```

- [ ] **Step 2: Run the test, verify it fails**

Run from `packages/workspace_runtime/`:

```bash
uv run pytest -v
```

Expected: failure on collection with `ImportError: cannot import name 'WORKSPACE_COMMAND_TYPES' from 'vibing_workspace_runtime'` (or equivalent).

- [ ] **Step 3: Replace `packages/workspace_runtime/src/vibing_workspace_runtime/__init__.py`**

```python
"""Workspace-side runtime skeleton.

The Workspace Runtime Agent owns Claude-session lifecycle (eventually:
launching Claude Code, PTY, streaming output, approval detection). This
module only defines the interface and a no-op implementation. No process
launches, no PTY, no I/O.
"""

from typing import Protocol

from vibing_protocol import Command, EventType, RuntimeEvent

__all__ = [
    "WORKSPACE_COMMAND_TYPES",
    "WorkspaceRuntime",
    "NoopWorkspaceRuntime",
]


WORKSPACE_COMMAND_TYPES: frozenset[str] = frozenset(
    {
        "start_claude_session",
        "stop_claude_session",
        "send_user_input",
        "resolve_approval",
    }
)


class WorkspaceRuntime(Protocol):
    """Receive a workspace-side command, emit zero or more runtime events."""

    def handle(self, command: Command) -> list[RuntimeEvent]: ...


class NoopWorkspaceRuntime:
    """No-op workspace runtime. Does not launch Claude Code, no PTY, no I/O."""

    _COMMAND_TO_EVENT: dict[str, EventType] = {
        "start_claude_session": "claude_session_started",
    }

    def handle(self, command: Command) -> list[RuntimeEvent]:
        event_type = self._COMMAND_TO_EVENT.get(command.type)
        if event_type is None:
            return []
        return [
            RuntimeEvent(
                event_type=event_type,
                source="workspace_runtime_agent",
                workspace_id=command.workspace_id,
                agent_session_id=command.agent_session_id,
            )
        ]
```

- [ ] **Step 4: Run the test, verify it passes**

Run from `packages/workspace_runtime/`:

```bash
uv run pytest -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Lint**

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add packages/workspace_runtime/src/vibing_workspace_runtime/__init__.py packages/workspace_runtime/tests/test_workspace_runtime.py packages/workspace_runtime/uv.lock
git commit -m "$(cat <<'EOF'
VIB-15 Add no-op WorkspaceRuntime skeleton in vibing_workspace_runtime

Defines WORKSPACE_COMMAND_TYPES, the WorkspaceRuntime Protocol, and a
NoopWorkspaceRuntime that maps start_claude_session to a
claude_session_started runtime event without launching any real
process.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Write `docs/runtime-boundaries.md`

**Files:**
- Create: `docs/runtime-boundaries.md`

- [ ] **Step 1: Create `docs/runtime-boundaries.md` with exactly the following content**

```markdown
# Vibing Runtime Boundaries

This document fixes the responsibilities of the Vibing MVP runtimes and the
shape of the messages that flow between them. It complements
`docs/domain-model.md` (which defines the product vocabulary) by tying that
vocabulary to runtime code.

The MVP has two runtimes:

- The **Host Runtime Worker**, owned by the backend (`apps/api`).
- The **Workspace Runtime Agent**, owned by `packages/workspace_runtime`.

The two communicate through a control plane carrying typed `Command` and
`RuntimeEvent` messages defined in `packages/protocol` (`vibing_protocol`).

## Host runtime responsibilities

The Host Runtime Worker is responsible for everything that lives outside the
workspace container, on the developer's machine.

- Preparing the workspace environment (eventually: invoking the Dev Container
  CLI, Docker, or Podman).
- Starting, stopping, and restarting the workspace runtime environment.
- Reporting workspace-level lifecycle outcomes through `RuntimeEvent`s:
  `workspace_started`, `workspace_failed`.
- Owning the host-side end of the control plane.

The host runtime does **not** know anything about Claude Code, PTY, or session
state. Those live in the workspace runtime.

## Workspace runtime responsibilities

The Workspace Runtime Agent is responsible for everything that happens inside
the workspace container, around one Claude Code session at a time.

- Starting the Claude Code session inside the workspace.
- Managing the PTY and session I/O.
- Routing user input back to Claude Code.
- Detecting questions and approval requests, and reporting them as
  `RuntimeEvent`s.
- Reporting session lifecycle and outcomes:
  `claude_session_started`, `claude_asked_question`, `approval_requested`,
  `approval_resolved`, `session_completed`, `session_failed`.
- Future: surfacing workspace Git state changes.

The workspace runtime does **not** know about container engines, the host
filesystem outside the workspace, or other workspaces.

## Control-plane message shapes

The control plane carries two message kinds, both defined in
`packages/protocol/src/vibing_protocol/`.

### `Command`

A request directed *at* a runtime. Fields:

- `type: CommandType` — one of the literal command names below.
- `workspace_id: str | None`
- `agent_session_id: str | None`
- `payload: dict[str, Any] | None`

`CommandType` literal:

```
start_workspace
stop_workspace
restart_workspace
start_claude_session
stop_claude_session
send_user_input
resolve_approval
```

### `RuntimeEvent`

A structured event emitted *from* a runtime. Fields:

- `id: str` (UUID4)
- `event_type: EventType` — one of the literal event names below.
- `source: RuntimeEventSource` — `host_runtime_worker` or
  `workspace_runtime_agent`.
- `workspace_id: str | None`
- `agent_session_id: str | None`
- `payload: dict[str, Any] | None`
- `created_at: str` (ISO 8601 UTC)

`EventType` literal:

```
workspace_started
workspace_failed
claude_session_started
claude_asked_question
approval_requested
approval_resolved
session_completed
session_failed
```

This document does not define a transport. Today the only consumer is the
backend's `runtime_events` table; future tickets add a dispatcher and/or
wire protocol between the host and workspace processes.

## Command routing

Each command type belongs to exactly one runtime.

| Command | Routed to |
| --- | --- |
| `start_workspace` | Host runtime |
| `stop_workspace` | Host runtime |
| `restart_workspace` | Host runtime |
| `start_claude_session` | Workspace runtime |
| `stop_claude_session` | Workspace runtime |
| `send_user_input` | Workspace runtime |
| `resolve_approval` | Workspace runtime |

The routing is exposed in code as `HOST_COMMAND_TYPES`
(`vibing_api.host_runtime`) and `WORKSPACE_COMMAND_TYPES`
(`vibing_workspace_runtime`). No dispatcher consumes those constants yet; a
future ticket adds one.

## Event-name alignment with the Product Foundation event model

`docs/domain-model.md` lists *example* runtime event names. The
type-checked, canonical set is `vibing_protocol.EventType` and is what the
implementation uses today. The mapping back to domain concepts:

| `EventType` | Source | Domain-model concept |
| --- | --- | --- |
| `workspace_started` | host_runtime_worker | workspace `running` |
| `workspace_failed` | host_runtime_worker | workspace `error`; produces `workspace_error` inbox event |
| `claude_session_started` | workspace_runtime_agent | agent session `running` |
| `claude_asked_question` | workspace_runtime_agent | produces `question` inbox event; session `waiting_for_user_input` |
| `approval_requested` | workspace_runtime_agent | new `approval_request`; produces `approval_request` inbox event |
| `approval_resolved` | workspace_runtime_agent | approval request `approved` or `rejected` |
| `session_completed` | workspace_runtime_agent | session `completed`; produces `completion` inbox event |
| `session_failed` | workspace_runtime_agent | session `failed`; produces `failure` inbox event |

`docs/domain-model.md` is not updated by this document. Future tickets that
expand the runtime surface (e.g. `git_status_changed`) extend `EventType`
and update this table at the same time.

## Intentionally out of scope for Product Foundation

The runtime skeletons present today do not implement:

- Docker, Podman, or any container engine call.
- Dev Container CLI invocation.
- Claude Code process launch or management.
- PTY handling, streaming output, terminal scrollback.
- Inbox-event side effects, approval-queue side effects.
- Git visibility or the changed-files view.
- Editor integration (VS Code, native, browser).
- Any long-running background worker.
- A control-plane transport (HTTP, queue, IPC) between the two runtimes.
- A `commands` SQLite table; commands are not persisted in the MVP.

Each of these lands in its own future ticket, against the contracts defined
above.
```

- [ ] **Step 2: Commit**

```bash
git add docs/runtime-boundaries.md
git commit -m "$(cat <<'EOF'
VIB-15 Document host and workspace runtime boundaries

Adds docs/runtime-boundaries.md describing host-side and workspace-side
responsibilities, the Command and RuntimeEvent message shapes, command
routing, the mapping from EventType back to the domain model, and what
is intentionally out of scope for Product Foundation.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Final verification pass

This task runs **no code changes** — only checks. If any step fails, fix the
underlying issue and re-run.

- [ ] **Step 1: Run the backend test suite + lint + type check**

Run from `apps/api/`:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Expected: pytest passes (all existing tests + the 3 new host_runtime tests); ruff passes; mypy passes against `src/`.

- [ ] **Step 2: Run the workspace_runtime suite + lint**

Run from `packages/workspace_runtime/`:

```bash
uv run pytest
uv run ruff check .
```

Expected: pytest passes (3 tests); ruff passes.

- [ ] **Step 3: Lint the protocol package**

Run from `apps/api/` (using its already-installed ruff):

```bash
uv run ruff check ../../packages/protocol
```

Expected: `All checks passed!` (or equivalent zero-error output).

- [ ] **Step 4: Sanity-check the diff for forbidden references**

Run from the repo root:

```bash
git diff main --name-only
git diff main -- 'apps/api/src' 'packages/' 'docs/' | grep -iE 'docker|podman|devcontainer cli|pty|subprocess|asyncio\.create_subprocess' || echo 'clean'
```

Expected: the `grep` line prints `clean`. If any match appears, investigate — the skeletons must contain zero references to real runtime infrastructure.

- [ ] **Step 5: Confirm all lockfiles are committed**

Run from the repo root:

```bash
git status
```

Expected: working tree clean (or only contains intended uncommitted files outside the scope of this plan). All three `uv.lock` files (`apps/api/uv.lock`, `packages/protocol/uv.lock`, `packages/workspace_runtime/uv.lock`) appear in `git ls-files`.

```bash
git ls-files | grep uv.lock
```

Expected output:

```
apps/api/uv.lock
packages/protocol/uv.lock
packages/workspace_runtime/uv.lock
```

If any of the three is missing, find the missing commit step and add it.

- [ ] **Step 6: No commit needed for this task**

This task only verifies; nothing should have changed on disk. If verification surfaced a real issue, fix it in a follow-up commit on the same branch.
