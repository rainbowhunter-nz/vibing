# VIB-15 — Host and workspace runtime skeleton + boundary docs

## Context

The Vibing MVP architecture splits runtime responsibility across two sides of a control plane:

- A **Host Runtime Worker** that owns workspace-lifecycle operations on the developer's machine (eventually: Dev Container CLI, Docker/Podman).
- A **Workspace Runtime Agent** that owns Claude-session lifecycle inside the workspace container (eventually: Claude Code process, PTY, session events).

The domain model (`docs/domain-model.md`, VIB-3) already establishes the vocabulary — workspace statuses, agent-session statuses, inbox events, approval requests, runtime event names. The backend has gone one step further and turned a subset of that vocabulary into actual Python types:

- `apps/api/src/vibing_api/core/commands.py` — `CommandType` literal + `COMMAND_TYPES` frozenset.
- `apps/api/src/vibing_api/core/runtime_events.py` — `EventType`, `RuntimeEventSource`, `RuntimeEvent` (pydantic), `record_runtime_event` (SQLite persistence), `list_runtime_events_by_*`.

What does **not** exist yet:

- No runtime-side code anywhere. `packages/protocol/` and `packages/workspace_runtime/` exist only as bare `uv init` placeholders (each is a single `main.py` printing "Hello from …"). Neither is referenced by `apps/api` or wired into any uv/pnpm workspace.
- No documentation describing what the host runtime vs. workspace runtime is *responsible for*, what control-plane messages flow between them, or what is intentionally out of scope.

VIB-15 fills both gaps with the **minimum amount of code**: a typed message-shape package, a no-op host runtime skeleton in the backend, a no-op workspace runtime skeleton in `packages/workspace_runtime`, and a boundary doc that ties everything to the domain model. Everything stays fake — no Docker, Podman, Dev Container CLI, Claude Code, PTY, or background workers.

## Goal

Produce three things:

1. **Documentation** — `docs/runtime-boundaries.md` listing host-side responsibilities, workspace-side responsibilities, the high-level control-plane message shapes, the alignment between runtime event names and the Product Foundation event model, and what's intentionally out of scope.
2. **A shared protocol package** — populate `packages/protocol` so it holds the canonical `Command` and `RuntimeEvent` message shapes plus the existing vocab literals. Both the backend and the workspace runtime depend on it via uv path sources. Refactor `vibing_api.core.commands` / `runtime_events` to re-export from protocol (existing import paths keep working).
3. **Two runtime skeletons** — `vibing_api.host_runtime` (in the backend) and `vibing_workspace_runtime` (in `packages/workspace_runtime`). Each defines its own `Protocol`-based handler interface (`HostRuntime` / `WorkspaceRuntime`) plus a no-op implementation that accepts a sample command and returns the corresponding sample event. One unit test per skeleton.

## Acceptance criteria (from VIB-15)

| Criterion | Treatment this ticket |
|---|---|
| Host-side runtime responsibilities are listed | `docs/runtime-boundaries.md` § Host responsibilities |
| Workspace-side runtime responsibilities are listed | `docs/runtime-boundaries.md` § Workspace responsibilities |
| Control-plane message shapes are sketched at a high level | `docs/runtime-boundaries.md` § Control-plane messages; concrete types in `vibing_protocol` |
| Runtime event names aligned with Product Foundation event model | `docs/runtime-boundaries.md` § Event-name alignment maps each `EventType` to a domain-model concept |
| States what is intentionally out of scope | `docs/runtime-boundaries.md` § Out of scope |
| Host runtime skeleton exists in the backend codebase | `apps/api/src/vibing_api/host_runtime/__init__.py` |
| Workspace runtime skeleton exists | `packages/workspace_runtime/src/vibing_workspace_runtime/__init__.py` |
| Skeleton interfaces/classes for receiving commands and emitting runtime events | `HostRuntime` Protocol + `NoopHostRuntime`; `WorkspaceRuntime` Protocol + `NoopWorkspaceRuntime` |
| Skeleton implementations are wired only to no-op or fake behavior | Both `Noop*Runtime.handle()` map a single command to an in-memory `RuntimeEvent` and return `[]` otherwise — no I/O, no DB, no subprocess |
| Unit tests prove the skeleton can accept a sample command and emit a sample runtime event without invoking real runtime infrastructure | `apps/api/tests/test_host_runtime.py`, `packages/workspace_runtime/tests/test_workspace_runtime.py` |

## Architecture

```
+------------------------+         +-----------------------------+
|  apps/api              |         |  packages/workspace_runtime |
|  (host side)           |         |  (workspace side)           |
|                        |         |                             |
|  vibing_api.           |         |  vibing_workspace_runtime   |
|    host_runtime        |         |    .WorkspaceRuntime        |
|      .HostRuntime      |         |    .NoopWorkspaceRuntime    |
|      .NoopHostRuntime  |         |                             |
+-----------+------------+         +--------------+--------------+
            \                                      /
             \         imports shapes             /
              \                                  /
               \      +-------------------+     /
                +--> |  packages/protocol | <--+
                     |                    |
                     |  vibing_protocol   |
                     |    Command         |
                     |    RuntimeEvent    |
                     |    CommandType     |
                     |    EventType       |
                     |    RuntimeEventSource
                     +-------------------+
```

`vibing_protocol` is pure data + types, no behavior. Each runtime defines its own handler `Protocol` (matches the per-runtime scope in the ticket and lets host/workspace diverge as they grow). Both runtimes return `list[RuntimeEvent]` from `handle(command: Command)` — same signature today, no shared base class.

## `vibing_protocol` package

### Layout

Convert `packages/protocol/` from the bare `uv init` placeholder to a `src/`-layout library:

```
packages/protocol/
  pyproject.toml          # name: vibing-protocol, build-system: uv_build
  README.md               # one-paragraph purpose statement
  src/vibing_protocol/
    __init__.py           # public re-exports
    commands.py           # Command, CommandType, COMMAND_TYPES
    runtime_events.py     # RuntimeEvent, EventType, RuntimeEventSource,
                          #   EVENT_TYPES, RUNTIME_EVENT_SOURCES,
                          #   InvalidRuntimeEventError
```

Delete `packages/protocol/main.py`.

Distribution name `vibing-protocol`, import package `vibing_protocol`. The directory name (`packages/protocol`) stays as-is — mirrors the `apps/api` → `vibing_api` convention already in the repo.

### `commands.py`

```python
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

The literal set is verbatim from `vibing_api/core/commands.py` (no name changes). `Command` is new — it's the typed message shape that both skeletons accept on `handle(...)`.

### `runtime_events.py`

```python
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
    """Raised when event_type or source is not in the allowed vocabulary."""


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

Difference from today's `vibing_api/core/runtime_events.py`:

- The `RuntimeEvent` model gains `default_factory` for `id` and `created_at` so any runtime can emit a fresh event without DB plumbing. The values are still strings (UUID4 hex / ISO 8601 UTC) — the SQLite schema is unchanged.
- The Literal types stay `EventType` / `RuntimeEventSource` (not `EVENT_TYPE`).

### `__init__.py`

```python
from .commands import Command, CommandType, COMMAND_TYPES
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

### `pyproject.toml`

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

`pydantic` is the only runtime dep. No dev group needed — protocol has no tests of its own; coverage comes through its consumers' tests.

## Backend refactor — `apps/api`

### `vibing_api/core/commands.py`

Replace contents with a thin re-export shim:

```python
"""Backwards-compatible re-exports. Canonical home: vibing_protocol.commands."""

from vibing_protocol.commands import COMMAND_TYPES, Command, CommandType

__all__ = ["COMMAND_TYPES", "Command", "CommandType"]
```

`from vibing_api.core.commands import COMMAND_TYPES` (used by tests) continues to resolve unchanged.

### `vibing_api/core/runtime_events.py`

Keep the persistence layer (`record_runtime_event`, `list_runtime_events_by_workspace`, `list_runtime_events_by_session`, `_row_to_event`), drop the local model + vocab definitions, import them from `vibing_protocol`:

```python
"""Runtime-event persistence over the runtime_events SQLite table.

Vocabulary and message shape live in vibing_protocol; this module owns only
the read/write helpers.
"""

import json
import sqlite3

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
    payload: dict | None = None,
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


def list_runtime_events_by_workspace(conn, workspace_id):
    ...  # body unchanged from today's implementation

def list_runtime_events_by_session(conn, agent_session_id):
    ...  # body unchanged from today's implementation
```

`_row_to_event` and the two `list_*` helpers keep their existing bodies verbatim — they're shown abbreviated above to focus on `record_runtime_event`, which is the only function that changes.

**Behaviour parity:** `record_runtime_event` previously generated `event_id` and `created_at` locally; now those come from `RuntimeEvent`'s default factories. Same uuid4 + ISO-8601-UTC format. All existing assertions in `apps/api/tests/test_runtime_events.py` continue to pass (they check `e.id` is truthy and `e.created_at` is truthy, not exact values).

### `apps/api/pyproject.toml`

Add the dependency and the path source:

```toml
[project]
# ... existing fields ...
dependencies = [
    "fastapi>=0.136.3",
    "pydantic-settings>=2.14.1",
    "rich>=15.0.0",
    "typer>=0.26.2",
    "uvicorn[standard]>=0.48.0",
    "vibing-protocol",                # <-- added
]

[tool.uv.sources]                     # <-- added
vibing-protocol = { path = "../../packages/protocol", editable = true }
```

`uv lock` in `apps/api` regenerates `uv.lock`. Editable install means edits in `packages/protocol/src` are picked up immediately by `apps/api` without reinstalling.

## Host runtime skeleton — `vibing_api.host_runtime`

### Layout

```
apps/api/src/vibing_api/host_runtime/
  __init__.py            # HostRuntime, NoopHostRuntime, HOST_COMMAND_TYPES
```

A small package (not a single module) for room to grow without a churn-y rename later.

### `__init__.py`

```python
"""Host-side runtime skeleton.

The Host Runtime Worker owns workspace-lifecycle operations (eventually:
Dev Container CLI, Docker/Podman). This module only defines the interface
and a no-op implementation for use until real lifecycle code lands.
"""

from typing import Protocol

from vibing_protocol import Command, EventType, RuntimeEvent

__all__ = ["HOST_COMMAND_TYPES", "HostRuntime", "NoopHostRuntime"]


HOST_COMMAND_TYPES: frozenset[str] = frozenset({
    "start_workspace",
    "stop_workspace",
    "restart_workspace",
})


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

Design notes:

- `HostRuntime` is a `typing.Protocol`, not an ABC — structural typing matches the duck-typed Python style elsewhere in the repo (e.g. callable injection in `vibing_api/dev/sample_data.py`).
- `_COMMAND_TO_EVENT` deliberately covers only one command (`start_workspace`). The skeleton honestly returns `[]` for everything else rather than fabricating richer no-op behaviour the ticket isn't asking for. Future tickets fill in `stop_workspace` → `workspace_failed` or similar as real lifecycle behaviour lands.
- `HOST_COMMAND_TYPES` lets future dispatcher code introspect which commands belong on the host side. Not consumed in this ticket.

### Test — `apps/api/tests/test_host_runtime.py`

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
    assert event.id  # default_factory populated
    assert event.created_at


def test_noop_host_runtime_returns_empty_for_unmapped_command() -> None:
    runtime = NoopHostRuntime()
    events = runtime.handle(Command(type="stop_workspace", workspace_id="ws1"))
    assert events == []


def test_host_command_types_cover_workspace_lifecycle() -> None:
    assert HOST_COMMAND_TYPES == {"start_workspace", "stop_workspace", "restart_workspace"}
```

Three tiny assertions, no DB, no docker, no fixtures. Covers the AC's "accept a sample command and emit a sample runtime event without invoking real runtime infrastructure."

## Workspace runtime skeleton — `packages/workspace_runtime`

### Layout

Convert from the bare placeholder:

```
packages/workspace_runtime/
  pyproject.toml          # name: vibing-workspace-runtime, build-system: uv_build
  README.md               # one-paragraph purpose statement
  src/vibing_workspace_runtime/
    __init__.py           # WorkspaceRuntime, NoopWorkspaceRuntime, WORKSPACE_COMMAND_TYPES
  tests/
    __init__.py
    test_workspace_runtime.py
```

Delete `packages/workspace_runtime/main.py`. Distribution rename: `workspace-runtime` → `vibing-workspace-runtime` (consistent with `vibing-protocol`, `vibing-api`). No external consumer references the old name (verified via grep at design time).

### `__init__.py`

```python
"""Workspace-side runtime skeleton.

The Workspace Runtime Agent owns Claude-session lifecycle (eventually:
launching Claude Code, PTY, streaming output, approval detection). This
module only defines the interface and a no-op implementation.
"""

from typing import Protocol

from vibing_protocol import Command, EventType, RuntimeEvent

__all__ = [
    "WORKSPACE_COMMAND_TYPES",
    "WorkspaceRuntime",
    "NoopWorkspaceRuntime",
]


WORKSPACE_COMMAND_TYPES: frozenset[str] = frozenset({
    "start_claude_session",
    "stop_claude_session",
    "send_user_input",
    "resolve_approval",
})


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

Mirror of `NoopHostRuntime`: maps only one command (`start_claude_session` → `claude_session_started`), returns `[]` otherwise. `agent_session_id` flows through because workspace events almost always belong to a session.

### `pyproject.toml`

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
dev = ["pytest>=9.0.3"]

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

`uv sync` in `packages/workspace_runtime` creates its own `.venv` and `uv.lock`. The two consumers (`apps/api`, `packages/workspace_runtime`) each have their own lockfile — there is no shared lock because we chose path deps over a uv workspace.

### Test — `tests/test_workspace_runtime.py`

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

## Documentation — `docs/runtime-boundaries.md`

A new doc, parallel to `docs/domain-model.md`. Structure:

1. **Purpose** — one paragraph. The host runtime and workspace runtime are two distinct processes (eventually) that talk via a control plane. This doc fixes responsibilities and the message shapes between them so future tickets have an unambiguous home.

2. **Host runtime responsibilities**

   - Preparing the workspace (eventually: Dev Container CLI / Docker / Podman invocation).
   - Starting, stopping, restarting the workspace runtime environment.
   - Reporting workspace-level lifecycle outcomes (`workspace_started`, `workspace_failed`).
   - Owning the host-side end of the control plane.

3. **Workspace runtime responsibilities**

   - Starting the Claude Code session inside the workspace.
   - Managing the PTY / session I/O.
   - Routing user input back to Claude Code.
   - Detecting questions and approval requests; reporting them as runtime events.
   - Reporting session lifecycle and outcomes (`claude_session_started`, `claude_asked_question`, `approval_requested`, `approval_resolved`, `session_completed`, `session_failed`).
   - Future: surfacing workspace Git state changes.

4. **Control-plane message shapes (high level)**

   The control plane carries two message kinds:

   - **`Command`** — request directed *at* a runtime. Fields: `type` (one of `CommandType`), `workspace_id`, `agent_session_id`, `payload`. Defined in `vibing_protocol.commands`.
   - **`RuntimeEvent`** — structured event emitted *from* a runtime. Fields: `id`, `event_type` (one of `EventType`), `source` (`host_runtime_worker` or `workspace_runtime_agent`), `workspace_id`, `agent_session_id`, `payload`, `created_at`. Defined in `vibing_protocol.runtime_events`.

   This ticket does **not** define a transport. Today the only consumer is the backend's persistence layer; future tickets add a dispatcher and/or wire protocol.

5. **Command routing**

   | Command | Routed to |
   |---|---|
   | `start_workspace`, `stop_workspace`, `restart_workspace` | Host runtime |
   | `start_claude_session`, `stop_claude_session`, `send_user_input`, `resolve_approval` | Workspace runtime |

   Exposed in code as `HOST_COMMAND_TYPES` (`vibing_api.host_runtime`) and `WORKSPACE_COMMAND_TYPES` (`vibing_workspace_runtime`).

6. **Event-name alignment with the Product Foundation event model**

   `docs/domain-model.md` lists *example* runtime event names (`session_started`, `question_detected`, `git_status_changed`, etc.). The canonical, type-checked set is `vibing_protocol.EventType` and is what the implementation uses today. The mapping:

   | `EventType` | Source | Domain-model concept |
   |---|---|---|
   | `workspace_started` | host_runtime_worker | workspace `running` |
   | `workspace_failed` | host_runtime_worker | workspace `error`; produces `workspace_error` inbox event |
   | `claude_session_started` | workspace_runtime_agent | agent session `running` |
   | `claude_asked_question` | workspace_runtime_agent | `question` inbox event; session `waiting_for_user_input` |
   | `approval_requested` | workspace_runtime_agent | new `approval_request`; produces `approval_request` inbox event |
   | `approval_resolved` | workspace_runtime_agent | approval request `approved`/`rejected` |
   | `session_completed` | workspace_runtime_agent | session `completed`; produces `completion` inbox event |
   | `session_failed` | workspace_runtime_agent | session `failed`; produces `failure` inbox event |

   The domain-model doc is unchanged in this ticket. Future tickets may extend `EventType` (e.g. `git_status_changed`) when the corresponding behaviour ships.

7. **Intentionally out of scope for Product Foundation**

   The runtime skeletons in this ticket do not implement:

   - Docker, Podman, or any container engine call.
   - Dev Container CLI invocation.
   - Claude Code process launch or management.
   - PTY handling, streaming output, terminal scrollback.
   - Inbox-event side effects, approval-queue side effects.
   - Git visibility, changed-files view.
   - Editor integration (VS Code / native / browser).
   - Any long-running background worker.
   - A control-plane transport (HTTP, queue, IPC) between the two runtimes.
   - A `commands` SQLite table; commands are not persisted in MVP.

## Testing & verification

Per-package checks (run from the package directory):

```bash
# Backend — refactor + host runtime
cd apps/api
uv sync
uv run pytest                          # all existing tests + new test_host_runtime.py
uv run ruff check .
uv run mypy src                        # already configured (mypy>=2.1.0 in dev deps)

# Workspace runtime
cd packages/workspace_runtime
uv sync
uv run pytest                          # new test_workspace_runtime.py
uv run ruff check .

# Protocol (no tests of its own; lint only)
cd packages/protocol
uv sync
uv run ruff check .
```

All three lock files (`apps/api/uv.lock`, `packages/workspace_runtime/uv.lock`, `packages/protocol/uv.lock`) are committed.

## Implementation order (sequencing)

1. **Stand up `vibing_protocol`.** Restructure `packages/protocol` into a src-layout library; write `commands.py`, `runtime_events.py`, `__init__.py`, `pyproject.toml`, `README.md`. Delete `main.py`. `uv lock` + `uv sync` succeed.
2. **Refactor backend core.** Edit `apps/api/pyproject.toml` to add the path dep; `uv lock`. Replace `vibing_api/core/commands.py` with the re-export shim. Refactor `vibing_api/core/runtime_events.py` to import from protocol + simplify `record_runtime_event`. Run `uv run pytest` — `test_runtime_events.py` must stay green unchanged.
3. **Add host runtime skeleton.** Create `vibing_api/host_runtime/__init__.py`. Write `tests/test_host_runtime.py`. `uv run pytest` green.
4. **Stand up `vibing_workspace_runtime`.** Restructure `packages/workspace_runtime` into src-layout; write `__init__.py`, `tests/test_workspace_runtime.py`, `pyproject.toml`, `README.md`. Delete `main.py`. `uv sync` + `uv run pytest` green.
5. **Write `docs/runtime-boundaries.md`.**
6. **Final pass:** `uv run ruff check .` in all three packages; `uv run mypy src` in `apps/api`.

Each step is independently committable; the order matters because step 2 depends on step 1, step 3 on step 2, etc.

## Out of scope (explicit)

- **No root uv workspace, no root `pyproject.toml`.** Path sources only, per the design decision recorded during brainstorming.
- **No transport.** `vibing_workspace_runtime` is not started as a process and is not reachable from the backend at runtime. A future ticket adds whatever transport the architecture needs.
- **No command persistence.** No `commands` SQLite table, no `record_command`. The existing `runtime_events` table remains the only control-plane persistence.
- **No dispatcher / orchestrator** that routes commands to host vs. workspace runtime by introspecting `HOST_COMMAND_TYPES` / `WORKSPACE_COMMAND_TYPES`. The constants exist for future tickets; nothing consumes them in this one.
- **No migration of existing API routes** to use `Command` / `HostRuntime`. The HTTP layer is untouched.
- **No changes to `docs/domain-model.md`.**
- **No frontend changes.**
- **No CI changes.** Devs run per-package commands manually, same as today.

## Risks and watchouts

- **Pydantic default factory for `RuntimeEvent.id` / `created_at`.** The change is a strict superset of today's behaviour (callers can still pass values explicitly), but worth a deliberate eye in review. Anyone reading a persisted row sees the same UUID4 + ISO-8601 shape as before.
- **Editable path sources require uv ≥ 0.11.16.** Already pinned via `uv_build`; the devcontainer ships `uv >= 0.11` per the README. Anyone on an older `uv` will get a clear error.
- **`record_runtime_event`'s `payload: dict | None` parameter is untyped.** The original was `dict[str, Any] | None`. The new module uses the same parametrised type — no narrowing change.
- **Three lockfiles, no shared resolution.** Diamond-dep skew between `apps/api` and `packages/workspace_runtime` is technically possible (e.g. each pins a different pydantic minor). For this ticket the only shared dep is `pydantic >= 2.0`, so in practice both resolvers pick the latest. If skew becomes a problem, revisit the workspace-vs-path-deps choice.
- **`Protocol`-based interfaces produce no runtime metaclass.** `isinstance(obj, HostRuntime)` requires `@runtime_checkable`, which we deliberately don't add — keeps the surface minimal. Tests use direct type annotation (`runtime: HostRuntime = NoopHostRuntime()`) which is mypy-checked, not runtime-checked.
- **Rename of `workspace-runtime` → `vibing-workspace-runtime`.** Distribution name change. No consumers exist, so this is free; if a downstream tool elsewhere references the old name, it will fail at install. Grep confirmed no references at design time.

## Done-when checklist

- `packages/protocol/` is a `src/`-layout library exporting `Command`, `RuntimeEvent`, vocab literals, and `InvalidRuntimeEventError`. `main.py` deleted. `uv.lock` committed.
- `apps/api/pyproject.toml` declares `vibing-protocol` as a dependency with a `tool.uv.sources` path entry. `apps/api/uv.lock` regenerated and committed.
- `vibing_api/core/commands.py` and `vibing_api/core/runtime_events.py` import from `vibing_protocol` and re-export the public names. Existing `apps/api/tests/test_runtime_events.py` passes unchanged.
- `apps/api/src/vibing_api/host_runtime/__init__.py` exports `HostRuntime`, `NoopHostRuntime`, `HOST_COMMAND_TYPES`. `apps/api/tests/test_host_runtime.py` passes.
- `packages/workspace_runtime/` is a `src/`-layout library exporting `WorkspaceRuntime`, `NoopWorkspaceRuntime`, `WORKSPACE_COMMAND_TYPES`. `main.py` deleted. Distribution renamed to `vibing-workspace-runtime`. `packages/workspace_runtime/tests/test_workspace_runtime.py` passes. `uv.lock` committed.
- `docs/runtime-boundaries.md` exists with the seven sections above.
- `uv run ruff check .` clean in all three packages. `uv run mypy src` clean in `apps/api`.
- No Docker, Podman, Dev Container CLI, Claude Code subprocess, or PTY code anywhere in the diff.
