# Runtime-Channel Deepening (D1–D3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen the runtime channel — one shared wire codec for both ends (D1), keep `RuntimeRegistry` testable through its interface (D2, already done), and move inbound snapshot persistence off the connection-registry module (D3).

**Architecture:** The Control Plane and the Devcontainer Runtime exchange JSON envelopes over one WebSocket. Today both ends duplicate the parse/serialize idiom, and the connection registry (`runtime_channel.py`) also carries inbound persistence + SSE broadcast. We introduce a shared `vibing_protocol.channel` codec (`encode`/`decode`) used by both ends, and split inbound persistence into its own `vibing_api.core.runtime_intake` module so the registry holds only connections.

**Tech Stack:** Python 3.13, FastAPI/Starlette, Pydantic v2, `websockets`, SQLite, pytest, ruff, mypy, uv.

## Global Constraints

- All checks must pass from repo root before every commit: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Simplicity First: minimum code that solves the problem; no speculative abstraction.
- DRY: no duplicated logic the codec is meant to remove.
- Keep all `CLAUDE.md` files coherent with the code in the same task that changes the code they describe.
- `CommandType` is a `StrEnum` with `auto()` values — compare with members, never raw strings.
- This work happens on branch `refactor-runtimes` (already checked out). Do not target `main`.
- End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- **Out of scope (do not do):** consolidating the 5 duplicate `_now()` helpers (separate cleanup), and dependency-injecting the persister into the route (D3 is relocation only).

---

## Current State (read before starting)

These are already implemented in the working tree and verified (ruff/format/mypy/pytest green), but **uncommitted**:

- **Purge:** deleted `tests/host_runtime/`, `tests/runtime_client/`, `src/vibing_api/core/commands.py`; doc fixes in `.claude/CLAUDE.md`, `src/vibing_api/CLAUDE.md`, `src/vibing_api/core/devcontainer_service.py`; test fixes in `tests/protocol/test_harness_vocab.py`, `tests/api/test_diagnostics.py`.
- **D2:** `RuntimeConnection` Protocol + `WebSocketRuntimeConnection` adapter + `RuntimeRegistry` storing connections in `src/vibing_api/core/runtime_channel.py`; route wraps the socket in `src/vibing_api/api/routes/runtime.py`; tests rewritten to use a `FakeRuntimeConnection` via `tests/api/conftest.py` fixtures (`devcontainer_id`, `connected_runtime`).

Task 1 commits this baseline so D1/D3 build on clean history.

## File Structure

**D1 — shared wire codec**
- Create: `src/vibing_protocol/channel.py` — `encode(envelope) -> str`, `decode(raw) -> dict | None`.
- Modify: `src/vibing_protocol/__init__.py` — export `encode`, `decode`.
- Modify: `src/vibing_devcontainer_runtime/runtime_client.py` — use codec; delete local `_parse_message`; drop `import json`.
- Modify: `src/vibing_api/api/routes/runtime.py` — use `decode`; delete local `_parse`; drop `import json`.
- Modify: `src/vibing_api/core/runtime_channel.py` — `WebSocketRuntimeConnection.send` uses `encode` + `send_text`.
- Create: `tests/protocol/test_channel.py`.
- Modify: `tests/api/test_runtime_channel.py` — adapter test asserts `send_text`.
- Docs: `src/vibing_protocol/CLAUDE.md`.

**D3 — relocate inbound persistence**
- Create: `src/vibing_api/core/runtime_intake.py` — `persist_harness_status`, `persist_delegated_runs`.
- Modify: `src/vibing_api/core/runtime_channel.py` — remove the two functions + now-unused imports.
- Modify: `src/vibing_api/api/routes/runtime.py` — import persist_* from `core.runtime_intake`.
- Create: `tests/api/test_runtime_intake.py` — the persistence tests (moved).
- Modify: `tests/api/test_runtime_channel.py` — keep only the adapter test.
- Docs: `src/vibing_api/CLAUDE.md`.

---

### Task 1: Checkpoint — commit the purge and D2 baseline

**Files:** none changed; commits existing working-tree changes.

**Interfaces:**
- Produces: clean git history with two commits so subsequent tasks have a stable base. No code symbols.

- [ ] **Step 1: Confirm the tree is green**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
Expected: all pass, `250 passed`.

- [ ] **Step 2: Commit the purge**

`git add` of the deleted `commands.py` path stages its removal. `src/vibing_api/CLAUDE.md` is committed with D2 in Step 3 (it carries both the purge doc fix and the D2 doc fix in one file).

```bash
git add tests/protocol/test_harness_vocab.py tests/api/test_diagnostics.py \
  .claude/CLAUDE.md src/vibing_api/core/devcontainer_service.py \
  src/vibing_api/core/commands.py
git commit -m "$(cat <<'EOF'
chore: purge deprecated-concept leftovers and weak tests

Remove dead core/commands.py re-export shim (zero importers), empty
host_runtime/runtime_client test dirs, and stale host-runtime doc
references. Trim tautological wire-value tests to a behavioral round-trip
and soften the brittle diagnostics ordered-list assertion.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Commit D2**

```bash
git add src/vibing_api/core/runtime_channel.py src/vibing_api/api/routes/runtime.py \
  src/vibing_api/CLAUDE.md tests/api/conftest.py tests/api/test_harnesses_api.py \
  tests/api/test_harness_install_api.py tests/api/test_runtime_channel.py
git commit -m "$(cat <<'EOF'
refactor(api): RuntimeRegistry holds RuntimeConnection, not raw WebSocket

Introduce a RuntimeConnection seam with a WebSocketRuntimeConnection adapter
that owns the command wire format; the registry now stores connections and
routes Commands to them. Route tests register a fake connection via the
public register() and assert on Command objects instead of poking the
private _connections dict and wire JSON.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify clean tree**

Run: `git status --short`
Expected: only the new plan file under `docs/superpowers/plans/` remains untracked (or nothing).

---

### Task 2: D1 — shared wire codec in `vibing_protocol`

**Files:**
- Create: `src/vibing_protocol/channel.py`
- Modify: `src/vibing_protocol/__init__.py`
- Modify: `src/vibing_protocol/CLAUDE.md`
- Test: `tests/protocol/test_channel.py`

**Interfaces:**
- Produces:
  - `vibing_protocol.channel.encode(envelope: pydantic.BaseModel) -> str` — `json.dumps(envelope.model_dump())`.
  - `vibing_protocol.channel.decode(raw: str) -> dict[str, Any] | None` — JSON-object parse, `None` on invalid JSON or non-object.
  - Both re-exported from `vibing_protocol` top level.

- [ ] **Step 1: Write the failing tests**

Create `tests/protocol/test_channel.py`:

```python
from vibing_protocol import Command, CommandEnvelope, CommandType, RegisterEnvelope, decode, encode


def test_decode_returns_dict_for_json_object():
    assert decode('{"type": "command"}') == {"type": "command"}


def test_decode_returns_none_for_invalid_json():
    assert decode("not json") is None


def test_decode_returns_none_for_non_object_json():
    assert decode("[1, 2, 3]") is None


def test_encode_then_decode_round_trips_register_envelope():
    envelope = RegisterEnvelope(devcontainer_id="dc-1")
    restored = decode(encode(envelope))
    assert restored is not None
    assert RegisterEnvelope.model_validate(restored) == envelope


def test_encode_then_decode_round_trips_command_envelope():
    envelope = CommandEnvelope(
        command=Command(
            type=CommandType.AUTHENTICATE_HARNESS,
            devcontainer_id="dc-1",
            payload={"harness": "codex"},
        )
    )
    restored = decode(encode(envelope))
    assert restored is not None
    assert CommandEnvelope.model_validate(restored) == envelope
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/protocol/test_channel.py -q`
Expected: FAIL — `ImportError: cannot import name 'decode' from 'vibing_protocol'`.

- [ ] **Step 3: Create the codec**

Create `src/vibing_protocol/channel.py`:

```python
"""Runtime-channel wire codec.

The Control Plane and the Devcontainer Runtime cross the same WebSocket, so
they share one codec for the JSON wire format of channel envelopes.
"""

import json
from typing import Any

from pydantic import BaseModel


def encode(envelope: BaseModel) -> str:
    """Serialize a channel envelope to its JSON wire string."""
    return json.dumps(envelope.model_dump())


def decode(raw: str) -> dict[str, Any] | None:
    """Parse a wire string to a message dict, or None if it is not a JSON object."""
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None
```

- [ ] **Step 4: Export from the package**

Modify `src/vibing_protocol/__init__.py`. Change the docstring line and add the channel import + exports:

```python
"""Shared control-plane message shapes and wire codec for the Vibing runtime channel."""

from .channel import decode, encode
from .commands import COMMAND_TYPES, Command, CommandType
from .messages import (
    CommandEnvelope,
    DelegatedRunItem,
    DelegatedRunsEnvelope,
    HarnessStatusEnvelope,
    HarnessStatusItem,
    RegisterEnvelope,
)

__all__ = [
    "COMMAND_TYPES",
    "Command",
    "CommandEnvelope",
    "CommandType",
    "DelegatedRunItem",
    "DelegatedRunsEnvelope",
    "HarnessStatusEnvelope",
    "HarnessStatusItem",
    "RegisterEnvelope",
    "decode",
    "encode",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/protocol/test_channel.py -q`
Expected: PASS (5 passed).

- [ ] **Step 6: Update `vibing_protocol` docs**

Modify `src/vibing_protocol/CLAUDE.md`. Replace the `## Files` and `## Context` sections to add `channel.py` and fix the stale "only AUTHENTICATE_HARNESS" note:

```markdown
## Files

- `commands.py`: `CommandType` StrEnum (`AUTHENTICATE_HARNESS`, `INSTALL_HARNESS`) + `Command` model.
- `messages.py`: WebSocket envelopes — `RegisterEnvelope`, `CommandEnvelope`, `HarnessStatusEnvelope`/`HarnessStatusItem`, `DelegatedRunsEnvelope`/`DelegatedRunItem`.
- `channel.py`: wire codec — `encode(envelope)`/`decode(raw)` shared by both ends of the runtime channel.

## Context

- `CommandType` is a `StrEnum`; values = wire strings via `auto()`. Compare with members, not raw strings.
- Both the Control Plane and the Devcontainer Runtime serialize/parse envelopes through `channel.encode`/`channel.decode`.
- Keep dependencies light: Pydantic + stdlib.
```

- [ ] **Step 7: Run full checks and commit**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
Expected: all pass.

```bash
git add src/vibing_protocol/channel.py src/vibing_protocol/__init__.py \
  src/vibing_protocol/CLAUDE.md tests/protocol/test_channel.py
git commit -m "$(cat <<'EOF'
feat(protocol): add shared runtime-channel wire codec (encode/decode)

One codec both ends use for the JSON envelope wire format, replacing the
duplicated parse/serialize idioms on the Control Plane and runtime sides.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: D1 — adopt the codec on the Devcontainer Runtime side

**Files:**
- Modify: `src/vibing_devcontainer_runtime/runtime_client.py`

**Interfaces:**
- Consumes: `vibing_protocol.decode`, `vibing_protocol.encode` (Task 2).
- Produces: no signature changes — `RuntimeChannelClient` public API unchanged; internal serialize/parse now route through the codec. Removes module-level `_parse_message`.

- [ ] **Step 1: Replace the import line**

In `src/vibing_devcontainer_runtime/runtime_client.py`, change line 19:

```python
from vibing_protocol import Command, CommandEnvelope, RegisterEnvelope, decode, encode
```

- [ ] **Step 2: Drop the now-unused `import json`**

Delete line 11 (`import json`). Leave the other imports (`asyncio`, `contextlib`, `signal`, etc.) intact.

- [ ] **Step 3: Route serialization and parsing through the codec**

Make these four replacements in the same file:

In `_run_session`, the register send:
```python
            await ws.send(encode(self._register))
```

In `_run_session`, the receive loop:
```python
                    message = decode(await ws.recv())
```

In `send_envelope`:
```python
        await ws.send(encode(envelope))
```

In `_make_send`:
```python
    def _make_send(self, ws: Any) -> SendFn:
        async def send(envelope: BaseModel) -> None:
            await ws.send(encode(envelope))

        return send
```

- [ ] **Step 4: Delete the local `_parse_message`**

Remove the entire function at the bottom of the file:

```python
def _parse_message(raw: str) -> dict[str, Any] | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None
```

- [ ] **Step 5: Run runtime tests**

Run: `uv run pytest tests/devcontainer_runtime -q`
Expected: PASS (no behavior change; `send_envelope` disconnect test and CLI tests still green).

- [ ] **Step 6: Run full checks and commit**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
Expected: all pass.

```bash
git add src/vibing_devcontainer_runtime/runtime_client.py
git commit -m "$(cat <<'EOF'
refactor(runtime): use shared channel codec in runtime_client

Replace local _parse_message and json.dumps(model_dump()) sites with
vibing_protocol.decode/encode.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: D1 — adopt the codec on the Control Plane side

**Files:**
- Modify: `src/vibing_api/api/routes/runtime.py`
- Modify: `src/vibing_api/core/runtime_channel.py`
- Modify: `tests/api/test_runtime_channel.py`

**Interfaces:**
- Consumes: `vibing_protocol.decode`, `vibing_protocol.encode` (Task 2).
- Produces: `WebSocketRuntimeConnection.send` now writes via `WebSocket.send_text(encode(...))` instead of `send_json(...)`. Wire bytes are identical; the adapter test asserts on `send_text`.

- [ ] **Step 1: Update the inbound parse in the route**

In `src/vibing_api/api/routes/runtime.py`:

Delete the local `_parse` helper (the function `def _parse(raw: str) -> dict[str, Any] | None: ...`).

Change the receive line inside `_serve` to:
```python
            message = decode(await websocket.receive_text())
```

Add `decode` to the protocol import (the existing `from vibing_protocol import ...` line) — final form:
```python
from vibing_protocol import DelegatedRunsEnvelope, HarnessStatusEnvelope, RegisterEnvelope, decode
```

Remove the now-unused `import json` at the top of the file.

- [ ] **Step 2: Update the outbound adapter to use the codec**

In `src/vibing_api/core/runtime_channel.py`, add `encode` to the protocol import:
```python
from vibing_protocol import Command, CommandEnvelope, DelegatedRunItem, HarnessStatusItem, encode
```

Change `WebSocketRuntimeConnection.send`:
```python
    async def send(self, command: Command) -> None:
        await self._websocket.send_text(encode(CommandEnvelope(command=command)))
```

- [ ] **Step 3: Update the adapter test to assert on `send_text`**

In `tests/api/test_runtime_channel.py`, replace the body of `test_websocket_runtime_connection_sends_command_envelope` with:

```python
def test_websocket_runtime_connection_sends_command_envelope() -> None:
    websocket = AsyncMock()
    connection = WebSocketRuntimeConnection(websocket)
    command = Command(
        type=CommandType.INSTALL_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex"},
    )

    asyncio.run(connection.send(command))

    websocket.send_text.assert_awaited_once()
    sent = json.loads(websocket.send_text.call_args[0][0])
    assert sent == CommandEnvelope(command=command).model_dump()
    assert sent["type"] == "command"
    assert sent["command"]["payload"] == {"harness": "codex"}
```

Add `import json` to that test file's imports (top of file, with the stdlib imports):
```python
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock
```

- [ ] **Step 4: Run the API tests**

Run: `uv run pytest tests/api -q`
Expected: PASS. In particular the WS endpoint tests (`test_devcontainer_runtime_connection.py`, `test_agent_channel.py`, `test_runtime_connection_invalidations.py`) stay green — `send_text` and `send_json` produce identical frames, which the runtime `decode`s the same way.

- [ ] **Step 5: Run full checks and commit**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
Expected: all pass.

```bash
git add src/vibing_api/api/routes/runtime.py src/vibing_api/core/runtime_channel.py \
  tests/api/test_runtime_channel.py
git commit -m "$(cat <<'EOF'
refactor(api): use shared channel codec on the control-plane side

Route inbound parse uses vibing_protocol.decode; WebSocketRuntimeConnection
serializes commands via encode + send_text. Both ends now share one wire
codec.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: D3 — relocate inbound persistence to `core/runtime_intake.py`

**Files:**
- Create: `src/vibing_api/core/runtime_intake.py`
- Modify: `src/vibing_api/core/runtime_channel.py`
- Modify: `src/vibing_api/api/routes/runtime.py`
- Modify: `src/vibing_api/CLAUDE.md`
- Create: `tests/api/test_runtime_intake.py`
- Modify: `tests/api/test_runtime_channel.py`

**Interfaces:**
- Consumes: `vibing_protocol.HarnessStatusItem`, `vibing_protocol.DelegatedRunItem`; `vibing_api.core.broadcaster.Broadcaster`.
- Produces:
  - `vibing_api.core.runtime_intake.persist_harness_status(devcontainer_id: str, items: list[HarnessStatusItem], broadcaster: Broadcaster | None = None) -> None`
  - `vibing_api.core.runtime_intake.persist_delegated_runs(devcontainer_id: str, items: list[DelegatedRunItem], broadcaster: Broadcaster | None = None) -> None`
  - After this task `runtime_channel.py` contains only `RuntimeConnection`, `WebSocketRuntimeConnection`, `RuntimeRegistry`.

- [ ] **Step 1: Create the intake module**

Create `src/vibing_api/core/runtime_intake.py`:

```python
"""Inbound runtime reports → read model.

The Devcontainer Runtime pushes Harness Status and Delegated Run snapshots up
the runtime channel; the Control Plane writes them directly to the read model
(ADR-0014, ADR-0016) and publishes an SSE invalidation in the same step.
"""

from vibing_protocol import DelegatedRunItem, HarnessStatusItem

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.database import get_connection
from vibing_api.repositories.delegated_runs import DelegatedRunRepository
from vibing_api.repositories.harness_status import HarnessStatusRepository


def persist_harness_status(
    devcontainer_id: str,
    items: list[HarnessStatusItem],
    broadcaster: Broadcaster | None = None,
) -> None:
    with get_connection() as conn:
        repo = HarnessStatusRepository(conn)
        for item in items:
            repo.upsert(
                devcontainer_id,
                item.name,
                installed=item.installed,
                authenticated=item.authenticated,
            )
        conn.commit()
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="harnesses", ids=[devcontainer_id]))


def persist_delegated_runs(
    devcontainer_id: str,
    items: list[DelegatedRunItem],
    broadcaster: Broadcaster | None = None,
) -> None:
    with get_connection() as conn:
        DelegatedRunRepository(conn).replace(devcontainer_id, items)
        conn.commit()
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="delegated_runs", ids=[devcontainer_id]))
```

- [ ] **Step 2: Trim `runtime_channel.py` to the registry only**

Replace the full contents of `src/vibing_api/core/runtime_channel.py` with:

```python
"""Per-devcontainer runtime connection registry."""

from typing import Protocol

from fastapi import WebSocket
from vibing_protocol import Command, CommandEnvelope, encode


class RuntimeConnection(Protocol):
    """A live link to one Devcontainer Runtime, able to receive Commands."""

    async def send(self, command: Command) -> None: ...


class WebSocketRuntimeConnection:
    """RuntimeConnection over the runtime's WebSocket; owns the wire format."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket

    async def send(self, command: Command) -> None:
        await self._websocket.send_text(encode(CommandEnvelope(command=command)))


class RuntimeRegistry:
    """Keyed runtime connections, one per devcontainer_id."""

    def __init__(self) -> None:
        self._connections: dict[str, RuntimeConnection] = {}

    def is_connected(self, devcontainer_id: str) -> bool:
        return devcontainer_id in self._connections

    def register(self, devcontainer_id: str, connection: RuntimeConnection) -> bool:
        if devcontainer_id in self._connections:
            return False
        self._connections[devcontainer_id] = connection
        return True

    def unregister(self, devcontainer_id: str, connection: RuntimeConnection) -> None:
        if self._connections.get(devcontainer_id) is connection:
            del self._connections[devcontainer_id]

    async def send_command(self, devcontainer_id: str, command: Command) -> None:
        connection = self._connections.get(devcontainer_id)
        if connection is None:
            raise RuntimeError(f"No runtime connection for {devcontainer_id!r}")
        await connection.send(command)
```

- [ ] **Step 3: Point the route at the new module**

In `src/vibing_api/api/routes/runtime.py`, change the runtime-channel import block so the registry comes from `runtime_channel` and the persist functions come from `runtime_intake`:

```python
from vibing_api.core.runtime_channel import RuntimeRegistry, WebSocketRuntimeConnection
from vibing_api.core.runtime_intake import persist_delegated_runs, persist_harness_status
```

- [ ] **Step 4: Move the persistence tests to a new file**

Create `tests/api/test_runtime_intake.py`:

```python
"""Unit tests for persist functions in runtime_intake."""

from pathlib import Path

import pytest

from vibing_api.core.broadcaster import SseEvent
from vibing_api.core.database import get_connection, init_db
from vibing_api.core.runtime_intake import persist_harness_status
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.harness_status import HarnessStatusRepository
from vibing_protocol import HarnessStatusItem


class _FakeBroadcaster:
    def __init__(self) -> None:
        self.published: list[SseEvent] = []

    def publish(self, event: SseEvent) -> None:
        self.published.append(event)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vibing_api.core.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    init_db()


def _seed_devcontainer() -> str:
    with get_connection() as conn:
        dc = DevcontainerRepository(conn).create(name="test", local_path="/tmp/test")
        conn.commit()
    return dc.id


def test_persist_harness_status_upserts_rows() -> None:
    dc_id = _seed_devcontainer()
    items = [
        HarnessStatusItem(name="claude", installed=True, authenticated=False),
        HarnessStatusItem(name="gh", installed=False, authenticated=False),
    ]
    persist_harness_status(dc_id, items)

    with get_connection() as conn:
        rows = HarnessStatusRepository(conn).list(dc_id)
    assert len(rows) == 2
    by_name = {r.name: r for r in rows}
    assert by_name["claude"].installed is True
    assert by_name["claude"].authenticated is False
    assert by_name["gh"].installed is False


def test_persist_harness_status_upserts_on_second_call() -> None:
    dc_id = _seed_devcontainer()
    persist_harness_status(
        dc_id, [HarnessStatusItem(name="claude", installed=False, authenticated=False)]
    )
    persist_harness_status(
        dc_id, [HarnessStatusItem(name="claude", installed=True, authenticated=True)]
    )

    with get_connection() as conn:
        rows = HarnessStatusRepository(conn).list(dc_id)
    assert len(rows) == 1
    assert rows[0].installed is True
    assert rows[0].authenticated is True


def test_persist_harness_status_publishes_harnesses_sse_event() -> None:
    dc_id = _seed_devcontainer()
    broadcaster = _FakeBroadcaster()
    persist_harness_status(
        dc_id, [HarnessStatusItem(name="gh", installed=True, authenticated=True)], broadcaster
    )

    assert len(broadcaster.published) == 1
    evt = broadcaster.published[0]
    assert evt.scope == "harnesses"
    assert evt.ids == [dc_id]


def test_persist_harness_status_no_broadcaster_is_ok() -> None:
    dc_id = _seed_devcontainer()
    # Must not raise when broadcaster is None
    persist_harness_status(
        dc_id, [HarnessStatusItem(name="gh", installed=True, authenticated=False)]
    )
```

- [ ] **Step 5: Reduce `test_runtime_channel.py` to the adapter test only**

Replace the full contents of `tests/api/test_runtime_channel.py` with:

```python
"""Unit tests for the WebSocketRuntimeConnection adapter in runtime_channel."""

import asyncio
import json
from unittest.mock import AsyncMock

from vibing_api.core.runtime_channel import WebSocketRuntimeConnection
from vibing_protocol import Command, CommandEnvelope, CommandType


def test_websocket_runtime_connection_sends_command_envelope() -> None:
    websocket = AsyncMock()
    connection = WebSocketRuntimeConnection(websocket)
    command = Command(
        type=CommandType.INSTALL_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex"},
    )

    asyncio.run(connection.send(command))

    websocket.send_text.assert_awaited_once()
    sent = json.loads(websocket.send_text.call_args[0][0])
    assert sent == CommandEnvelope(command=command).model_dump()
    assert sent["type"] == "command"
    assert sent["command"]["payload"] == {"harness": "codex"}
```

- [ ] **Step 6: Update `vibing_api` docs**

In `src/vibing_api/CLAUDE.md`, update the `core/runtime_channel.py` bullet and add a `core/runtime_intake.py` bullet right after it:

```markdown
  - `core/runtime_channel.py`: `RuntimeRegistry` holds one `RuntimeConnection` per `devcontainer_id` and sends `command`s to it; `WebSocketRuntimeConnection` is the real adapter and owns the command wire format (via `vibing_protocol.encode`).
  - `core/runtime_intake.py`: inbound `harness_status`/`delegated_runs` snapshots → direct read-model writes + SSE invalidation.
```

- [ ] **Step 7: Run full checks**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
Expected: all pass, `pytest` count unchanged from end of Task 4 (the 4 persistence tests moved files, the adapter test stayed).

- [ ] **Step 8: Commit**

```bash
git add src/vibing_api/core/runtime_intake.py src/vibing_api/core/runtime_channel.py \
  src/vibing_api/api/routes/runtime.py src/vibing_api/CLAUDE.md \
  tests/api/test_runtime_intake.py tests/api/test_runtime_channel.py
git commit -m "$(cat <<'EOF'
refactor(api): move inbound persistence to core/runtime_intake

runtime_channel.py now holds only the connection registry and its adapter;
persist_harness_status/persist_delegated_runs live in runtime_intake, with
their tests. One concern per module.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] Run the full suite once more: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q` — expect all green.
- [ ] `grep -rn "json.dumps\|json.loads" src/vibing_api/api/routes/runtime.py src/vibing_devcontainer_runtime/runtime_client.py` — expect no matches (codec owns it).
- [ ] `grep -rn "persist_harness_status\|persist_delegated_runs" src/vibing_api/core/runtime_channel.py` — expect no matches (moved to runtime_intake).
- [ ] `git log --oneline -6` — expect: purge, D2, D1 codec, D1 runtime, D1 control-plane, D3.
