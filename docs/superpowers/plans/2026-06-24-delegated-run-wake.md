# Delegated-Run Completion Wakes the Main Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the main harness spawn a detached Delegated Run, go idle, and be auto-woken with the result via a background `vibing delegated wait` Bash command that blocks on a new `await_run` MCP tool.

**Architecture:** Add a per-run terminal `asyncio.Event` to `DelegatedRunManager` and an `await_run(run_id, timeout)` long-poll; expose it as an `await_run` MCP tool; ship a thin streamable-HTTP MCP-client CLI (`vibing delegated wait`) that loops the tool until terminal. The harness runs that CLI as a background Bash command — its completion is what wakes the idle agent (no Control Plane, no channel).

**Tech Stack:** Python 3.13, `uv`, `asyncio`, `mcp` (FastMCP server + streamable-HTTP client), `typer` + `rich`, `pytest`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-24-delegated-run-wake-design.md`.
- Do **not** touch `spawn` / `get_status` / `get_result` / `stop` behavior, the runtime WebSocket client, or the Control-Plane / ADR-0016 observation path.
- Terminal statuses are exactly `completed` | `failed` | `stopped`; `running` is the only non-terminal status.
- Follow repo conventions: `typer` + `rich` for CLI, `logzero` for logging; self-explanatory code, comment only the non-obvious (`.claude/CLAUDE.md`).
- Checks must pass from repo root: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Run all Python via `uv run`. Do not hand-edit `pyproject.toml` dependencies (`mcp`, `typer`, `rich`, `httpx` are already deps).

---

### Task 1: `await_run` + terminal event in `DelegatedRunManager`

**Files:**
- Modify: `src/vibing_devcontainer_runtime/delegated_runs.py`
- Test: `tests/devcontainer_runtime/test_delegated_runs.py`

**Interfaces:**
- Consumes: existing `_Run`, `_await_run`, `stop`, `get_result`, `_get` in `delegated_runs.py`.
- Produces: `async DelegatedRunManager.await_run(run_id: str, timeout: float | None = None) -> dict[str, Any]`. Returns the `get_result` payload (`{"run_id", "status", "result", "error"}`) when terminal; returns `{"run_id": run_id, "status": "running", "timed_out": True}` on timeout; raises `KeyError` on unknown `run_id`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/devcontainer_runtime/test_delegated_runs.py` (reuses `_mgr`, `ScriptedProcess`, `CompletedCommand` already in the file):

```python
def test_await_run_returns_when_detached_run_completes():
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "late result", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=factory)
        await mgr.spawn("codex", "m", "p", detached=True)
        waiter = asyncio.ensure_future(mgr.await_run("run-1"))
        assert not waiter.done()  # blocks while running
        gate.set()
        out = await waiter
        assert out["status"] == "completed"
        assert out["result"] == "late result"

    asyncio.run(scenario())


def test_await_run_returns_immediately_when_already_terminal():
    async def scenario():
        mgr = _mgr(factory=lambda *a: ScriptedProcess(CompletedCommand(0, "done", "")))
        await mgr.spawn("codex", "m", "p")  # blocking -> already completed
        out = await mgr.await_run("run-1")
        assert out["status"] == "completed"
        assert out["result"] == "done"

    asyncio.run(scenario())


def test_await_run_times_out_while_running():
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=factory)
        await mgr.spawn("codex", "m", "p", detached=True)
        out = await mgr.await_run("run-1", timeout=0.01)
        assert out == {"run_id": "run-1", "status": "running", "timed_out": True}
        gate.set()
        await mgr.wait_all()

    asyncio.run(scenario())


def test_await_run_returns_when_run_stopped():
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    async def scenario():
        mgr = _mgr(factory=factory)
        await mgr.spawn("codex", "m", "p", detached=True)
        waiter = asyncio.ensure_future(mgr.await_run("run-1"))
        await mgr.stop("run-1")
        out = await waiter
        assert out["status"] == "stopped"

    asyncio.run(scenario())


def test_await_run_unknown_id_raises():
    async def scenario():
        mgr = _mgr()
        with pytest.raises(KeyError):
            await mgr.await_run("nope")

    asyncio.run(scenario())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/devcontainer_runtime/test_delegated_runs.py -k await_run -v`
Expected: FAIL — `AttributeError: 'DelegatedRunManager' object has no attribute 'await_run'`.

- [ ] **Step 3: Add the `done` event to `_Run`**

In `delegated_runs.py`, add a field to the `_Run` dataclass (alongside `task`):

```python
    done: asyncio.Event = field(default_factory=asyncio.Event)
```

- [ ] **Step 4: Fire `done` on every terminal transition in `_await_run`**

Replace the body of `_await_run` so the terminal event is set on the completed, failed, and cancelled (→ stopped) paths via a `finally` guard. The existing `await self._emit()` stays at the end (it is skipped on cancel exactly as today):

```python
    async def _await_run(self, run: _Run, descriptor: HarnessDescriptor) -> None:
        assert run.process is not None
        try:
            result = await run.process.wait()
        except asyncio.CancelledError:
            run.status = "stopped"
            raise
        except Exception as exc:
            run.status = "failed"
            run.error = {"exit_code": None, "stderr_tail": str(exc)[-4000:]}
        else:
            if result.returncode == 0:
                run.status = "completed"
                run.result = descriptor.extract_result(result.stdout)
            else:
                run.status = "failed"
                run.error = {"exit_code": result.returncode, "stderr_tail": result.stderr[-4000:]}
        finally:
            if run.status != "running":
                run.done.set()
        await self._emit()
```

- [ ] **Step 5: Fire `done` in `stop` and add `await_run`**

In `stop()`, after the status is settled to `stopped`, ensure the event fires (covers the no-task already-terminal case too). Change the tail of `stop`:

```python
        if run.status == "running":
            run.status = "stopped"
        run.done.set()
        await self._emit()
        return {"run_id": run_id, "status": run.status}
```

Then add the method (place it after `get_result`):

```python
    async def await_run(self, run_id: str, timeout: float | None = None) -> dict[str, Any]:
        run = self._get(run_id)  # KeyError on unknown run
        if run.status != "running":
            return self.get_result(run_id)
        try:
            await asyncio.wait_for(run.done.wait(), timeout)
        except asyncio.TimeoutError:
            return {"run_id": run_id, "status": "running", "timed_out": True}
        return self.get_result(run_id)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/devcontainer_runtime/test_delegated_runs.py -v`
Expected: PASS (new `await_run` tests + all existing tests).

- [ ] **Step 7: Lint, type-check, commit**

```bash
uv run ruff format src tests && uv run ruff check src tests && uv run mypy src
git add src/vibing_devcontainer_runtime/delegated_runs.py tests/devcontainer_runtime/test_delegated_runs.py
git commit -m "feat(runtime): await_run long-poll on DelegatedRunManager"
```

---

### Task 2: `await_run` MCP tool

**Files:**
- Modify: `src/vibing_devcontainer_runtime/mcp_server.py`
- Test: `tests/devcontainer_runtime/test_mcp_server.py`

**Interfaces:**
- Consumes: `DelegatedRunManager.await_run(run_id, timeout=...)` from Task 1.
- Produces: MCP tool `await_run(run_id: str, timeout_seconds: float = 25.0) -> dict[str, Any]`.

- [ ] **Step 1: Write the failing tests**

In `tests/devcontainer_runtime/test_mcp_server.py`, extend `FakeDelegatedRuns` with an `await_run` method and add assertions:

```python
    async def await_run(self, run_id, timeout=25.0):
        self.awaited = (run_id, timeout)
        return {"run_id": run_id, "status": "completed", "result": "ok", "error": {}}
```

Update `test_tools_are_registered` to include `await_run` in the expected set, and add:

```python
def test_await_run_forwards_args_and_returns_result():
    runs = FakeDelegatedRuns()
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), runs)
    _content, result = asyncio.run(
        mcp.call_tool("await_run", {"run_id": "run-1", "timeout_seconds": 5.0})
    )
    assert runs.awaited == ("run-1", 5.0)
    assert result["status"] == "completed" and result["result"] == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/devcontainer_runtime/test_mcp_server.py -v`
Expected: FAIL — `await_run` not in registered tools / unknown tool `await_run`.

- [ ] **Step 3: Add the tool**

In `mcp_server.py`, add after the `get_result` tool (note the kwarg name maps `timeout_seconds` → manager `timeout`):

```python
    @mcp.tool()
    async def await_run(run_id: str, timeout_seconds: float = 25.0) -> dict[str, Any]:
        """Block until a detached Delegated Run finishes; return its result. Re-call if timed_out."""
        return await delegated_runs.await_run(run_id, timeout=timeout_seconds)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/devcontainer_runtime/test_mcp_server.py -v`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff format src tests && uv run ruff check src tests && uv run mypy src
git add src/vibing_devcontainer_runtime/mcp_server.py tests/devcontainer_runtime/test_mcp_server.py
git commit -m "feat(runtime): await_run MCP tool"
```

---

### Task 3: `vibing delegated wait` CLI

**Files:**
- Create: `src/vibing_cli/delegated.py`
- Modify: `src/vibing_cli/__init__.py`
- Test: `tests/cli/test_delegated.py` (create)

**Interfaces:**
- Consumes: the `await_run` MCP tool (Task 2) on the runtime streamable-HTTP server.
- Produces: `vibing delegated wait <run_id>` command. Internals: `async _await_once(mcp_url, run_id, timeout_seconds) -> dict[str, Any]` (one MCP `await_run` call, returns its payload) and `async _poll(mcp_url, run_id, timeout_seconds) -> dict[str, Any]` (loops `_await_once` while payload has `timed_out`, returns the terminal payload). `_await_once` is the seam tests monkeypatch.

- [ ] **Step 1: Write the failing tests**

Create `tests/cli/test_delegated.py`:

```python
import pytest
from typer.testing import CliRunner

from vibing_cli import app
from vibing_cli import delegated

runner = CliRunner()


def test_wait_loops_past_timeout_then_prints_terminal(monkeypatch):
    calls = {"n": 0}

    async def fake_await_once(mcp_url, run_id, timeout_seconds):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"run_id": run_id, "status": "running", "timed_out": True}
        return {"run_id": run_id, "status": "completed", "result": "the answer", "error": {}}

    monkeypatch.setattr(delegated, "_await_once", fake_await_once)
    result = runner.invoke(app, ["delegated", "wait", "run-1"])
    assert result.exit_code == 0
    assert calls["n"] == 3
    assert "completed" in result.stdout
    assert "the answer" in result.stdout


def test_wait_exits_nonzero_when_wait_errors(monkeypatch):
    async def boom(mcp_url, run_id, timeout_seconds):
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(delegated, "_await_once", boom)
    result = runner.invoke(app, ["delegated", "wait", "run-1"])
    assert result.exit_code == 1
    assert "server unreachable" in result.stdout + str(result.exception or "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cli/test_delegated.py -v`
Expected: FAIL — `ModuleNotFoundError: vibing_cli.delegated` / no `delegated` command.

- [ ] **Step 3: Create the CLI module**

Create `src/vibing_cli/delegated.py`:

```python
"""`vibing delegated wait <run_id>`: block on the runtime MCP server until a Delegated Run ends.

A backgroundable shim — Claude Code can't background an MCP call, so the harness runs this as a
background Bash command and is auto-woken when it returns. Loops `await_run` past each bounded
server-side timeout until the run is terminal.
"""

import asyncio
from typing import Annotated, Any

import typer
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from rich.console import Console

app = typer.Typer(no_args_is_help=True, help="Delegated Run helpers (MCP client).")

_out = Console()
_err = Console(stderr=True)

DEFAULT_MCP_URL = "http://127.0.0.1:8848/mcp"


async def _await_once(mcp_url: str, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    """One `await_run` MCP call; returns the tool's structured payload."""
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "await_run", {"run_id": run_id, "timeout_seconds": timeout_seconds}
            )
            return dict(result.structuredContent or {})


async def _poll(mcp_url: str, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    while True:
        payload = await _await_once(mcp_url, run_id, timeout_seconds)
        if not payload.get("timed_out"):
            return payload


@app.command("wait")
def wait(
    run_id: str,
    mcp_url: Annotated[
        str, typer.Option(envvar="VIBING_MCP_URL", help="Runtime MCP server URL.")
    ] = DEFAULT_MCP_URL,
    timeout_seconds: Annotated[
        float, typer.Option(help="Per-call long-poll timeout.")
    ] = 25.0,
) -> None:
    """Block until the Delegated Run finishes, then print its result."""
    try:
        payload = asyncio.run(_poll(mcp_url, run_id, timeout_seconds))
    except Exception as exc:
        _err.print(f"[bold red]✗ await_run failed[/bold red]: {exc}")
        raise typer.Exit(1) from exc

    status = payload.get("status")
    if status == "completed":
        _out.print(f"[bold green]✓ {run_id} completed[/bold green]")
        _out.print(payload.get("result") or "")
    else:
        _out.print(f"[bold yellow]{run_id} {status}[/bold yellow]")
        if payload.get("error"):
            _out.print(str(payload["error"]))
```

- [ ] **Step 4: Mount the sub-app**

In `src/vibing_cli/__init__.py`, add the import and mount alongside the other `add_typer` calls:

```python
from vibing_cli import delegated
```

```python
app.add_typer(delegated.app, name="delegated")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/cli/test_delegated.py -v`
Expected: PASS.

- [ ] **Step 6: Verify the MCP client imports resolve**

Run: `uv run python -c "from mcp import ClientSession; from mcp.client.streamable_http import streamablehttp_client; print('ok')"`
Expected: prints `ok`. If the import path differs in the installed `mcp` version, fix the import in `delegated.py` (search the installed package: `uv run python -c "import mcp.client.streamable_http"`), keep `_await_once` the only place that touches the transport, and re-run Step 5.

- [ ] **Step 7: Lint, type-check, commit**

```bash
uv run ruff format src tests && uv run ruff check src tests && uv run mypy src
git add src/vibing_cli/delegated.py src/vibing_cli/__init__.py tests/cli/test_delegated.py
git commit -m "feat(cli): vibing delegated wait blocks on await_run"
```

---

### Task 4: Docs coherence + ADR

**Files:**
- Modify: `src/vibing_devcontainer_runtime/CLAUDE.md`
- Modify: `src/vibing_cli/CLAUDE.md`
- Create: `docs/adr/0021-delegated-run-completion-wakes-the-main-harness-via-background-shell.md`
- Modify: `docs/adr/CLAUDE.md`

**Interfaces:**
- Consumes: the behavior built in Tasks 1–3. No code.

- [ ] **Step 1: Update the runtime CLAUDE.md**

In `src/vibing_devcontainer_runtime/CLAUDE.md`, in the `mcp_server.py` bullet, add `await_run` to the tool list and note it long-polls. Change the tool list to:
`list_harnesses`/`spawn`/`get_status`/`get_result`/`await_run`/`stop`, and append a sentence:
`await_run` long-polls until a detached run is terminal (`completed`/`failed`/`stopped`) so the main harness can be woken by a background-shell waiter instead of polling.

- [ ] **Step 2: Update the CLI CLAUDE.md**

In `src/vibing_cli/CLAUDE.md`, under "Files" add a bullet for `delegated.py`, under "Commands" add:
`vibing delegated wait <run_id>`: blocks on the runtime MCP server's `await_run` until the run ends; run as a background Bash command so its completion wakes the main harness. MCP URL from `--mcp-url` / `VIBING_MCP_URL` (default `http://127.0.0.1:8848/mcp`; inside the devcontainer use `http://host.docker.internal:8848/mcp`).
And under "Context" note: `delegated.py` is an MCP client (not API-HTTP glue like `client/`).

- [ ] **Step 3: Write the ADR**

Create `docs/adr/0021-delegated-run-completion-wakes-the-main-harness-via-background-shell.md`:

```markdown
# Delegated-run completion wakes the main harness via a background-shell blocking wait

The main harness (interactive Claude Code) spawns detached Delegated Runs (ADR-0011/0013) and
needed to poll `get_status`/`get_result` to learn the outcome. We want the harness to idle (the
user keeps interacting) and resume automatically when a run finishes.

Only three things wake an idle interactive Claude Code session: a background Bash command
finishing, a background subagent returning, or a channel notification. The background-task wake
is harness-internal — the harness only re-activates from children it launched; no external
process can trigger it. So we ride that mechanism: the harness runs `vibing delegated wait
<run_id>` as a background Bash command, which long-polls a new `await_run` MCP tool until the run
is terminal; its exit wakes the harness with the result.

`await_run` is backed by a per-run terminal `asyncio.Event` in `DelegatedRunManager` and a
bounded-timeout long-poll (the CLI re-issues on timeout). MCP tool calls cannot be backgrounded
in the TUI, so the backgroundable shim is a CLI (`vibing delegated wait`), a thin streamable-HTTP
MCP client. A background subagent calling `await_run` directly is an alternative but spins a whole
agent context to block.

Rejected: **channels** (a second MCP server + research-preview flag + org policy — overkill for
this); **Control-Plane involvement** (the CP already observes runs via ADR-0016, but this is a
pure runtime/MCP concern and routing the wake through the CP adds coupling); launching the harness
itself as a background Bash job (bypasses `DelegatedRunManager`'s cap, auth, descriptor argv, and
CP observation).

Consequences: the wake only fires while the harness terminal is open and idle (close it → missed,
re-check via `get_status` on return). `spawn`/`get_status`/`get_result`/`stop` and the ADR-0016
observation path are unchanged.

Status: accepted
```

- [ ] **Step 4: Add the ADR index entry**

In `docs/adr/CLAUDE.md`, append under the existing list:

```markdown
- [0021](0021-delegated-run-completion-wakes-the-main-harness-via-background-shell.md) — A detached Delegated Run's completion wakes the idle main harness via a background `vibing delegated wait` Bash command that long-polls a new `await_run` MCP tool (per-run terminal event in `DelegatedRunManager`); not channels, not the Control Plane. Extends 0011/0013.
```

- [ ] **Step 5: Verify and commit**

```bash
uv run ruff check src tests && uv run pytest -q
git add src/vibing_devcontainer_runtime/CLAUDE.md src/vibing_cli/CLAUDE.md docs/adr/
git commit -m "docs: ADR-0021 + CLAUDE.md coherence for delegated-run wake"
```

---

## Self-Review

**Spec coverage:**
- `await_run` manager method + terminal event → Task 1. ✓
- `await_run` MCP tool → Task 2. ✓
- `vibing delegated wait` CLI (loop, exit codes, URL/env) → Task 3. ✓
- Untouched spawn/status/result/stop/CP path → guaranteed by Global Constraints; no task modifies them. ✓
- Edge cases (already-terminal, unknown id, stop-during-wait, timeout loop) → Task 1 tests + Task 3 loop. ✓ (runtime-restart loss surfaces as an `await_run` error → CLI non-zero, covered by Task 3 error test.)
- Docs coherence + ADR → Task 4. ✓

**Placeholder scan:** none — every code/step is concrete.

**Type consistency:** `await_run(run_id, timeout=...)` (manager) ↔ tool kwarg `timeout_seconds` mapped explicitly ↔ CLI `_await_once`/`_poll` payload dict with `timed_out`/`status`/`result`/`error` keys, consistent across tasks.
