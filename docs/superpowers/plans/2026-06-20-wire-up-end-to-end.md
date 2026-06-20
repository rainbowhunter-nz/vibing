# Wire Up Control Plane + Devcontainer Runtime + UI (End-to-End) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the three already-built layers talk end-to-end against a real container, AND bridge the backend↔devcontainer-runtime gaps (explicit `install_harness`; Control Plane observation of Delegated Runs). Leave the frontend↔backend gaps deferred.

**Architecture:** Primarily an **integration + verification** pass plus two **backend↔runtime** feature bridges. All three layers are implemented and unit-tested in isolation but have never run together. Work: (1) small dev-loop wiring fixes + a benign empty delegated-runs stub for the UI, (2) amend ADR-0015 and add an `install_harness` Command + a runtime→CP Delegated-Run snapshot report with CP-side storage, (3) a dev-loop verification gate, (4) a production-image gate proving the full round trip.

**Tech Stack:** FastAPI + SQLite (Control Plane), asyncio WebSocket client + FastMCP (Devcontainer Runtime), Pydantic envelopes (`vibing_protocol`), React 19 + Vite + Tailwind (Web UI), Dev Container CLI + docker-outside-of-docker, `uv` (Python), `pnpm` (web), Typer (CLI).

## Global Constraints

- **Bridge backend↔runtime only; do NOT bridge frontend↔backend.** The React app is not modified and is not wired to new data. RailActivity keeps reading the always-empty GET `/delegated-runs` stub; the new Delegated-Run storage is verified via repository/tests, not surfaced to the UI yet.
- **Wire only; delete nothing in the frontend.** Install button and RailActivity stay.
- **Delegated Runs are still spawned/observed in-container via MCP** (ADR-0011/0013). ADR-0016 (this plan) adds a *read-only CP projection* fed by runtime-pushed snapshots; runs remain non-durable.
- **Reporting model = snapshot, not deltas.** The runtime sends the full current run list per devcontainer; the CP replaces its stored set for that devcontainer. Mirrors `harness_status`.
- **Single origin in production:** backend serves API at `/api/v1` and the built SPA from `/` on port `8080`. Frontend uses relative `/api/v1` — no CORS.
- **Credentials are host-captured, CLI-only.** No frontend credential UI; real host-login file capture is NOT built. Demo uses `vibing harness creds set <name> --blob '<json>'`.
- **Managed harnesses only** are installed/authenticated by the runtime: `codex`, `cursor`. `claude-code` is the main harness, never managed.
- Python checks (repo root): `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Web checks (`apps/web`): `pnpm test`, `pnpm build`.
- Keep `CONTEXT.md` and the ADR index coherent with the codebase.

---

## File Structure

**Modify:**
- `apps/web/vite.config.ts` — dev proxy `:8000` → `:8080`.
- `src/vibing_api/core/errors.py` — `RuntimeUnavailableError` default wording.
- `src/vibing_api/main.py` — register the delegated-runs router.
- `src/vibing_protocol/commands.py` / `messages.py` / `__init__.py` — `INSTALL_HARNESS`; `DelegatedRunItem` + `DelegatedRunsEnvelope`.
- `src/vibing_devcontainer_runtime/harness_manager.py` — `install()`.
- `src/vibing_devcontainer_runtime/command_handler.py` — handle `INSTALL_HARNESS`.
- `src/vibing_devcontainer_runtime/delegated_runs.py` — `started_at`, `list_runs()`, `report` hook + emit on transitions.
- `src/vibing_devcontainer_runtime/cli.py` — wire the report hook + initial report.
- `src/vibing_api/core/schema.py` — `delegated_runs` table, bump `SCHEMA_VERSION` to `"7"`.
- `src/vibing_api/core/broadcaster.py` — add `"delegated_runs"` scope.
- `src/vibing_api/api/routes/runtime.py` — handle the `delegated_runs` envelope.
- `src/vibing_api/core/runtime_channel.py` — `persist_delegated_runs()`.
- `src/vibing_api/api/routes/harnesses.py` — `POST .../install`.
- `src/vibing_cli/client/harnesses.py` — `vibing harness install`.
- `CONTEXT.md`, `docs/adr/CLAUDE.md`.

**Create:**
- `docs/adr/0016-control-plane-observes-delegated-runs-via-runtime-snapshots-and-adds-install-harness.md`
- `src/vibing_api/api/schemas/delegated_runs.py`
- `src/vibing_api/api/routes/delegated_runs.py`
- `src/vibing_api/repositories/delegated_runs.py`
- Tests: `tests/api/test_delegated_runs_api.py`, `tests/api/test_delegated_runs_repository.py`, `tests/api/test_delegated_runs_channel.py`, `tests/api/test_harness_install_api.py`, `tests/protocol/test_delegated_runs_envelope.py`.

---

### Task 1: Fix the dev-loop Vite proxy target

The frontend talks to relative `/api/v1`; in the dev loop Vite proxies it, but targets `:8000` while the backend serves `:8080` (`core/config.py`, `deploy/supervisord.conf`). Every API call + the SSE stream 404 in the dev loop until this matches.

**Files:**
- Modify: `apps/web/vite.config.ts`

**Interfaces:**
- Produces: dev server proxying `/api/v1` (HTTP + SSE) → `http://localhost:8080`.

- [ ] **Step 1: Update the proxy target**

In `apps/web/vite.config.ts`:

```ts
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 2: Verify the web build still type-checks**

Run: `cd apps/web && pnpm build`
Expected: build succeeds, no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/vite.config.ts
git commit -m "fix(web): point dev proxy at backend port 8080"
```

---

### Task 2: Add the benign empty delegated-runs endpoint (frontend-facing stub)

RailActivity calls `GET /api/v1/devcontainers/{id}/delegated-runs`. Add an endpoint that returns an empty list (404 only when the devcontainer is unknown). This stays empty for now — the FE↔BE bridge (serving stored runs) is deferred. Storage lands in Task 7.

**Files:**
- Create: `src/vibing_api/api/schemas/delegated_runs.py`
- Create: `src/vibing_api/api/routes/delegated_runs.py`
- Modify: `src/vibing_api/main.py`
- Test: `tests/api/test_delegated_runs_api.py`

**Interfaces:**
- Consumes: `get_connection` (`vibing_api.core.database`), `DevcontainerRepository` (`vibing_api.repositories.devcontainers`), `DevcontainerNotFoundError` (`vibing_api.core.errors`).
- Produces: `GET /api/v1/devcontainers/{devcontainer_id}/delegated-runs` → `DelegatedRunList(items: list[DelegatedRunItem])`. `DelegatedRunItem` mirrors the frontend `DelegatedRun`: `run_id: str`, `harness: str`, `model: str`, `status: str`, `result: str | None`, `error: dict | None`, `started_at: str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_delegated_runs_api.py` (reuse the `client` fixture from `tests/api/conftest.py` if present, else mirror `tests/api/test_harnesses_api.py`):

```python
def test_delegated_runs_empty_for_known_devcontainer(client):
    created = client.post(
        "/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"}
    ).json()
    resp = client.get(f"/api/v1/devcontainers/{created['id']}/delegated-runs")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_delegated_runs_404_for_unknown_devcontainer(client):
    resp = client.get("/api/v1/devcontainers/does-not-exist/delegated-runs")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/api/test_delegated_runs_api.py -v`
Expected: FAIL (404 route-not-registered for both).

- [ ] **Step 3: Create the schema**

Create `src/vibing_api/api/schemas/delegated_runs.py`:

```python
from pydantic import BaseModel


class DelegatedRunItem(BaseModel):
    run_id: str
    harness: str
    model: str
    status: str
    result: str | None = None
    error: dict | None = None
    started_at: str


class DelegatedRunList(BaseModel):
    items: list[DelegatedRunItem]
```

- [ ] **Step 4: Create the route**

Create `src/vibing_api/api/routes/delegated_runs.py`:

```python
from fastapi import APIRouter

from vibing_api.api.schemas.delegated_runs import DelegatedRunList
from vibing_api.core.database import get_connection
from vibing_api.core.errors import DevcontainerNotFoundError
from vibing_api.repositories.devcontainers import DevcontainerRepository

router = APIRouter(tags=["delegated-runs"], prefix="/devcontainers")


@router.get("/{devcontainer_id}/delegated-runs", response_model=DelegatedRunList)
def list_delegated_runs(devcontainer_id: str) -> DelegatedRunList:
    # FE↔BE deferred: the Control Plane stores Delegated Runs (ADR-0016) but does
    # not yet surface them to the web UI. This endpoint stays empty so RailActivity
    # reads as genuinely empty; flipping it to read DelegatedRunRepository is the
    # deferred frontend-facing step.
    with get_connection() as conn:
        if DevcontainerRepository(conn).get(devcontainer_id) is None:
            raise DevcontainerNotFoundError(devcontainer_id)
    return DelegatedRunList(items=[])
```

- [ ] **Step 5: Register the router**

In `src/vibing_api/main.py`, add `delegated_runs` to the route imports and the `include_router` loop (after `harnesses.router`):

```python
from vibing_api.api.routes import (
    config,
    delegated_runs,
    devcontainers,
    diagnostics,
    events,
    harnesses,
    health,
    runtime,
    settings as settings_route,
    status,
)
```

```python
        harnesses.router,
        delegated_runs.router,
        settings_route.router,
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest tests/api/test_delegated_runs_api.py -v`
Expected: PASS (both).

- [ ] **Step 7: Lint/format/types + commit**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`
Expected: clean.

```bash
git add src/vibing_api/api/schemas/delegated_runs.py src/vibing_api/api/routes/delegated_runs.py src/vibing_api/main.py tests/api/test_delegated_runs_api.py
git commit -m "feat(api): add empty delegated-runs endpoint to satisfy UI contract"
```

---

### Task 3: Correct the RuntimeUnavailableError default wording

`RuntimeUnavailableError`'s default message says "No Host Runtime Worker is connected" — a retired concept (ADR-0014).

**Files:**
- Modify: `src/vibing_api/core/errors.py:53`

- [ ] **Step 1: Update the default**

```python
    def __init__(self, message: str = "No Devcontainer Runtime is connected") -> None:
```

- [ ] **Step 2: Run error-response tests**

Run: `uv run pytest tests/api/test_error_responses.py -q`
Expected: PASS. If a test asserts the old string verbatim, update it in this commit.

- [ ] **Step 3: Commit**

```bash
git add src/vibing_api/core/errors.py tests/api/test_error_responses.py
git commit -m "chore(api): drop retired Host Runtime Worker wording from runtime error"
```

---

### Task 4: ADR-0016 + CONTEXT.md + ADR index (governing decision for the bridges)

Record the decision that governs Tasks 5–7 before implementing them. This amends ADR-0015's "in-container only / CP does not track" stance for Delegated Runs and introduces the `install_harness` Command.

**Files:**
- Create: `docs/adr/0016-control-plane-observes-delegated-runs-via-runtime-snapshots-and-adds-install-harness.md`
- Modify: `docs/adr/CLAUDE.md`, `CONTEXT.md`

**Interfaces:**
- Produces: documentation only. No code symbols.

- [ ] **Step 1: Write the ADR**

Create the ADR file with this content:

```markdown
# The Control Plane observes Delegated Runs via runtime-pushed snapshots; add install_harness

ADR-0015 scoped Delegated Runs as **in-container only** — observable solely by the main
harness through MCP, with the Control Plane explicitly not tracking them. To let the Control
Plane (and, later, the web UI) observe delegated activity, we **amend that stance**: the
Devcontainer Runtime now reports Delegated Runs up the existing runtime WebSocket, and the
Control Plane keeps a **read-only projection** of them.

**Reporting is a snapshot, not a delta stream.** On every run state change (spawn→running,
terminal, stop) and once on connect, the runtime sends the *full current run list* for its
devcontainer as a `delegated_runs` envelope. The Control Plane **replaces** its stored set for
that devcontainer. This mirrors `harness_status`: idempotent, ordering-tolerant, and
self-healing — a runtime that restarts (losing its in-memory runs) reconnects and replaces the
CP set with its current (likely empty) state, so the projection never drifts permanently. Deltas
were rejected: they need per-event delivery guarantees the single best-effort WebSocket does not
provide, and they complicate restart reconciliation.

The Control Plane stores the projection in a `delegated_runs` read-model table, written directly
(ADR-0014 style: no event log) when a snapshot arrives, and publishes a `delegated_runs` SSE
invalidation. Runs remain **non-durable and in-container-spawned**: the CP projection is
best-effort and may be empty or stale immediately after a runtime restart. We accept this — it is
observation, not a system of record.

We also add an **`install_harness` Command** (Control Plane → Runtime), separate from
`authenticate_harness` (which still installs-on-demand). It calls the per-harness adapter's
existing `install()` and reports `harness_status` back, giving an explicit install action without
delivering credentials.

This re-scopes ADR-0013 (Delegated Runs are now reported up, as a projection) and amends
ADR-0015's in-container-only stance. The web UI is **not** wired to the stored runs yet — the
frontend-facing `GET /delegated-runs` stays an empty stub; that exposure is deferred. The runtime
channel grows a fourth message kind (`delegated_runs`, Runtime → Control Plane) and the Command
vocabulary grows `install_harness`.

Status: accepted
```

- [ ] **Step 2: Update the ADR index**

In `docs/adr/CLAUDE.md`, append under the list:

```markdown
- [0016](0016-control-plane-observes-delegated-runs-via-runtime-snapshots-and-adds-install-harness.md) — The Control Plane keeps a read-only projection of Delegated Runs fed by runtime-pushed snapshots over the WebSocket; adds the `install_harness` Command. Amends 0015 (in-container-only), re-scopes 0013.
```

And annotate the existing 0013 and 0015 lines by appending to each: `(Amended by [0016].)`

- [ ] **Step 3: Update CONTEXT.md**

Make these edits in `CONTEXT.md`:

- **Delegated Run** entry — replace the "In-container only … the Control Plane does not track it." sentence with:
  `Spawned and observed in-container via MCP (`get_status`/`get_result`); additionally reported to the Control Plane as a read-only snapshot projection over the runtime channel (ADR-0016). Non-durable — the CP projection is best-effort and may be empty after a runtime restart.`
- **Command** entry — change `The extensible runtime channel; today only `authenticate_harness`.` to `The extensible runtime channel; today `authenticate_harness` and `install_harness`.`
- **Notes** (final paragraph) — change `carries exactly three message kinds: `register`, `command` (Control Plane → Runtime), and `harness_status` (Runtime → Control Plane).` to `carries four message kinds: `register`, `command` (Control Plane → Runtime), `harness_status` and `delegated_runs` (Runtime → Control Plane).`

- [ ] **Step 4: Coherence check + commit**

Run: `grep -rn "does not track" CONTEXT.md; grep -rn "0016" docs/adr/CLAUDE.md`
Expected: the "does not track" line is gone from CONTEXT.md; the 0016 index line is present.

```bash
git add docs/adr/0016-*.md docs/adr/CLAUDE.md CONTEXT.md
git commit -m "docs(adr): ADR-0016 — CP observes delegated runs; add install_harness"
```

---

### Task 5: Protocol — `INSTALL_HARNESS` command + Delegated-Run envelopes

**Files:**
- Modify: `src/vibing_protocol/commands.py`, `src/vibing_protocol/messages.py`, `src/vibing_protocol/__init__.py`
- Test: `tests/protocol/test_delegated_runs_envelope.py`, `tests/protocol/test_harness_vocab.py`

**Interfaces:**
- Produces:
  - `CommandType.INSTALL_HARNESS` (wire value `"install_harness"`).
  - `DelegatedRunItem(run_id: str, harness: str, model: str, status: str, result: str | None = None, error: dict | None = None, started_at: str)`.
  - `DelegatedRunsEnvelope(type: Literal["delegated_runs"], devcontainer_id: str, items: list[DelegatedRunItem])`.

- [ ] **Step 1: Write failing tests**

Create `tests/protocol/test_delegated_runs_envelope.py`:

```python
from vibing_protocol import DelegatedRunItem, DelegatedRunsEnvelope


def test_delegated_runs_envelope_roundtrip():
    env = DelegatedRunsEnvelope(
        devcontainer_id="dc-1",
        items=[
            DelegatedRunItem(
                run_id="run-1", harness="codex", model="gpt-5-codex",
                status="running", started_at="2026-06-20T00:00:00+00:00",
            )
        ],
    )
    dumped = env.model_dump()
    assert dumped["type"] == "delegated_runs"
    again = DelegatedRunsEnvelope.model_validate(dumped)
    assert again.items[0].run_id == "run-1"
    assert again.items[0].result is None and again.items[0].error is None
```

Append to `tests/protocol/test_harness_vocab.py`:

```python
def test_install_harness_in_vocab():
    from vibing_protocol import CommandType

    assert CommandType.INSTALL_HARNESS.value == "install_harness"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/protocol -v`
Expected: FAIL (ImportError / missing attribute).

- [ ] **Step 3: Add the command type**

In `src/vibing_protocol/commands.py`, add to `CommandType`:

```python
class CommandType(StrEnum):
    """Control-plane command vocabulary. Values are the wire strings."""

    AUTHENTICATE_HARNESS = auto()
    INSTALL_HARNESS = auto()
```

- [ ] **Step 4: Add the envelopes**

In `src/vibing_protocol/messages.py`, add after `HarnessStatusEnvelope`:

```python
class DelegatedRunItem(BaseModel):
    run_id: str
    harness: str
    model: str
    status: str
    result: str | None = None
    error: dict | None = None
    started_at: str


class DelegatedRunsEnvelope(BaseModel):
    type: Literal["delegated_runs"] = "delegated_runs"
    devcontainer_id: str
    items: list[DelegatedRunItem]
```

- [ ] **Step 5: Export them**

In `src/vibing_protocol/__init__.py`, add `DelegatedRunItem` and `DelegatedRunsEnvelope` to the `from .messages import (...)` block and to `__all__` (keep `__all__` alphabetised).

- [ ] **Step 6: Run to verify pass + checks**

Run: `uv run pytest tests/protocol -v && uv run mypy src`
Expected: PASS, clean.

- [ ] **Step 7: Commit**

```bash
git add src/vibing_protocol tests/protocol/test_delegated_runs_envelope.py tests/protocol/test_harness_vocab.py
git commit -m "feat(protocol): add install_harness command and delegated_runs envelope"
```

---

### Task 6: Runtime — `install_harness` handler + Delegated-Run reporting

Add an explicit install path and make the runtime push Delegated-Run snapshots over the channel.

**Files:**
- Modify: `src/vibing_devcontainer_runtime/harness_manager.py`, `command_handler.py`, `delegated_runs.py`, `cli.py`
- Test: `tests/devcontainer_runtime/test_command_handler_harness.py`, `tests/devcontainer_runtime/test_delegated_runs.py`

**Interfaces:**
- Consumes: `CommandType.INSTALL_HARNESS`, `DelegatedRunItem`, `DelegatedRunsEnvelope` (Task 5); `HarnessAdapter.install/is_installed` (existing).
- Produces:
  - `HarnessManager.install(harness: str) -> HarnessStatus`.
  - `DelegatedRunManager.list_runs() -> list[dict]` (each: `run_id, harness, model, status, result(str|None), error(dict|None), started_at`).
  - `DelegatedRunManager.report: Callable[[], Awaitable[None]] | None` — settable hook invoked on every run-state transition and reportable on connect.

- [ ] **Step 1: Write failing tests**

Append to `tests/devcontainer_runtime/test_command_handler_harness.py` (follow the file's existing fake adapter + `sent` capture style):

```python
async def test_install_command_installs_and_reports(make_handler):
    handler, fake_codex, sent = make_handler()  # adapt to this file's existing helper
    fake_codex.installed = False
    from vibing_protocol import Command, CommandType

    await handler.handle(
        Command(type=CommandType.INSTALL_HARNESS, payload={"harness": "codex"}),
        sent.append_send,
    )
    assert fake_codex.install_called
    assert sent.last.items[0].name == "codex"
    assert sent.last.items[0].installed is True
```

(If `test_command_handler_harness.py` builds the handler inline rather than via a `make_handler` fixture, replicate that exact construction instead — reuse, don't invent a new harness.)

Append to `tests/devcontainer_runtime/test_delegated_runs.py`:

```python
async def test_report_hook_fires_and_lists_runs(make_manager):
    # make_manager: this file's existing factory for DelegatedRunManager with a fake
    # process factory + authenticated adapter. Reuse it.
    reports: list[list[dict]] = []

    manager = make_manager()

    async def _report():
        reports.append(manager.list_runs())

    manager.report = _report
    out = await manager.spawn("codex", "m", "do it")  # blocking run
    assert out["status"] in {"completed", "failed"}
    # at least a running snapshot and a terminal snapshot were emitted
    assert len(reports) >= 2
    last = manager.list_runs()
    assert last[0]["run_id"] == out["run_id"]
    assert last[0]["started_at"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/devcontainer_runtime/test_command_handler_harness.py tests/devcontainer_runtime/test_delegated_runs.py -v`
Expected: FAIL (no `install`, no `report`/`list_runs`).

- [ ] **Step 3: Add `HarnessManager.install`**

In `src/vibing_devcontainer_runtime/harness_manager.py`, add:

```python
    async def install(self, harness: str) -> HarnessStatus:
        adapter = self._adapters[harness]  # KeyError on unknown harness
        if not await adapter.is_installed():
            await adapter.install()
        return await self._status(adapter)
```

- [ ] **Step 4: Handle `INSTALL_HARNESS` in the command handler**

In `src/vibing_devcontainer_runtime/command_handler.py`, replace the body of `handle`:

```python
    async def handle(self, command: Command, send: SendFn) -> None:
        payload = command.payload or {}
        harness = payload.get("harness", "")
        if command.type == CommandType.AUTHENTICATE_HARNESS:
            status = await self._harness.authenticate(harness, payload.get("credentials") or {})
        elif command.type == CommandType.INSTALL_HARNESS:
            status = await self._harness.install(harness)
        else:
            logger.info("Ignoring unsupported command: %s", command.type)
            return
        await send(self._envelope([status]))
```

- [ ] **Step 5: Add reporting to `DelegatedRunManager`**

In `src/vibing_devcontainer_runtime/delegated_runs.py`:

Add imports + a timestamp helper near the top:

```python
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

ReportFn = Callable[[], Awaitable[None]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

Add `started_at` to `_Run`:

```python
    started_at: str = ""
```

In `__init__`, accept and store the hook (default `None`):

```python
        report: ReportFn | None = None,
```
```python
        self.report = report
```

Set `started_at` and emit a "running" snapshot in `spawn` — set the timestamp where the run is created, and emit just before the `if detached:` branch:

```python
        run = _Run(run_id=f"run-{self._counter}", harness=harness, model=model, started_at=_now())
        self._runs[run.run_id] = run

        argv = adapter.build_spawn_argv(model, prompt)
        run.process = self._factory(argv, cwd or self._workspace, adapter.spawn_env())

        await self._emit()
        if detached:
```

Emit on terminal transitions — restructure `_await_run` so non-cancelled paths emit once at the end:

```python
    async def _await_run(self, run: _Run, adapter: HarnessAdapter) -> None:
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
                run.result = adapter.extract_result(result.stdout)
            else:
                run.status = "failed"
                run.error = {"exit_code": result.returncode, "stderr_tail": result.stderr[-4000:]}
        await self._emit()
```

Emit after `stop` sets a terminal status — add before the `return` in `stop`:

```python
        if run.status == "running":
            run.status = "stopped"
        await self._emit()
        return {"run_id": run_id, "status": run.status}
```

Add `_emit` and `list_runs`:

```python
    async def _emit(self) -> None:
        if self.report is not None:
            await self.report()

    def list_runs(self) -> list[dict[str, Any]]:
        return [
            {
                "run_id": r.run_id,
                "harness": r.harness,
                "model": r.model,
                "status": r.status,
                "result": r.result or None,
                "error": r.error or None,
                "started_at": r.started_at,
            }
            for r in self._runs.values()
        ]
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest tests/devcontainer_runtime/test_command_handler_harness.py tests/devcontainer_runtime/test_delegated_runs.py -v`
Expected: PASS.

- [ ] **Step 7: Wire the report hook in the CLI**

In `src/vibing_devcontainer_runtime/cli.py`, update imports and `_serve_async`. Add to imports:

```python
from vibing_protocol import DelegatedRunItem, DelegatedRunsEnvelope, RegisterEnvelope
```

Replace the client/manager wiring block so the runtime reports harness status **and** delegated runs on connect, and pushes run snapshots as they change:

```python
    register = RegisterEnvelope(devcontainer_id=devcontainer_id)
    handler = HarnessCommandHandler(harness_manager, devcontainer_id)

    delegated_runs = DelegatedRunManager(
        adapters,
        real_process_factory,
        devcontainer_id=devcontainer_id,
        workspace=workspace,
    )

    async def _report_runs() -> None:
        items = [DelegatedRunItem(**r) for r in delegated_runs.list_runs()]
        try:
            await client.send_envelope(
                DelegatedRunsEnvelope(devcontainer_id=devcontainer_id, items=items)
            )
        except Exception:
            logger.exception("Failed to report delegated runs")

    async def _on_registered() -> None:
        await handler.report_all(client.send_envelope)
        await _report_runs()

    client = RuntimeChannelClient(
        control_plane_url, register, handler.handle, on_registered=_on_registered
    )
    delegated_runs.report = _report_runs

    mcp: FastMCP = build_mcp_server(harness_manager, delegated_runs, host=mcp_host, port=mcp_port)

    await asyncio.gather(
        client.run(),
        mcp.run_streamable_http_async(),
    )
```

(`client` is referenced inside `_report_runs`/`_on_registered` before its assignment, but those coroutines only run after connect, by which point `client` is bound. If `RuntimeChannelClient`'s `on_registered` must be a zero-arg callable returning an awaitable, pass `on_registered=_on_registered` directly — it already matches that shape; confirm against `runtime_client.py` and wrap in `lambda: _on_registered()` only if the signature requires it.)

- [ ] **Step 8: Run the runtime suite + CLI test + checks**

Run: `uv run pytest tests/devcontainer_runtime -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS, clean. (If `tests/devcontainer_runtime/test_cli.py` asserts the old wiring shape, update it to the new `_on_registered` wiring.)

- [ ] **Step 9: Commit**

```bash
git add src/vibing_devcontainer_runtime tests/devcontainer_runtime
git commit -m "feat(runtime): explicit install_harness + push delegated-run snapshots"
```

---

### Task 7: Control Plane — persist Delegated-Run snapshots + handle the envelope + install endpoint/CLI

Store runtime-pushed snapshots, publish a `delegated_runs` SSE invalidation, and add the `install_harness` Command path (HTTP endpoint + CLI). The frontend-facing GET stays empty (Task 2).

**Files:**
- Modify: `src/vibing_api/core/schema.py`, `core/broadcaster.py`, `core/runtime_channel.py`, `api/routes/runtime.py`, `api/routes/harnesses.py`, `src/vibing_cli/client/harnesses.py`
- Create: `src/vibing_api/repositories/delegated_runs.py`
- Test: `tests/api/test_delegated_runs_repository.py`, `tests/api/test_delegated_runs_channel.py`, `tests/api/test_harness_install_api.py`

**Interfaces:**
- Consumes: `DelegatedRunsEnvelope` (Task 5); `Broadcaster`/`SseEvent`, `get_connection`, `RuntimeRegistry.send_command` (existing).
- Produces:
  - Table `delegated_runs(devcontainer_id, run_id, harness, model, status, result, error, started_at, updated_at)`, PK `(devcontainer_id, run_id)`.
  - `DelegatedRunRepository(conn)` with `replace(devcontainer_id, items: list[DelegatedRunItem]) -> None` and `list(devcontainer_id) -> list[DelegatedRunRow]` (`DelegatedRunRow` fields mirror `DelegatedRunItem`).
  - `persist_delegated_runs(devcontainer_id, items, broadcaster=None)` in `core/runtime_channel.py`.
  - `POST /api/v1/devcontainers/{id}/harnesses/{name}/install` → 202, sends `CommandType.INSTALL_HARNESS`.

- [ ] **Step 1: Write failing tests**

Create `tests/api/test_delegated_runs_repository.py`:

```python
from vibing_protocol import DelegatedRunItem

from vibing_api.repositories.delegated_runs import DelegatedRunRepository


def _item(run_id, status="running"):
    return DelegatedRunItem(
        run_id=run_id, harness="codex", model="m", status=status,
        started_at="2026-06-20T00:00:00+00:00",
    )


def test_replace_is_a_full_snapshot(db_conn):  # reuse the api conftest db fixture
    repo = DelegatedRunRepository(db_conn)
    repo.replace("dc-1", [_item("run-1"), _item("run-2")])
    db_conn.commit()
    assert {r.run_id for r in repo.list("dc-1")} == {"run-1", "run-2"}
    repo.replace("dc-1", [_item("run-3", status="completed")])
    db_conn.commit()
    rows = repo.list("dc-1")
    assert [r.run_id for r in rows] == ["run-3"]
    assert rows[0].status == "completed"
```

Create `tests/api/test_delegated_runs_channel.py` (mirror `tests/api/test_runtime_channel.py`'s WebSocket-register-then-send pattern):

```python
def test_delegated_runs_snapshot_is_persisted(client, app):
    created = client.post(
        "/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"}
    ).json()
    dc_id = created["id"]
    with client.websocket_connect("/api/v1/runtime/agent/ws") as ws:
        ws.send_json({"type": "runtime_registered", "devcontainer_id": dc_id})
        ws.receive_json()  # {"type": "registered"}
        ws.send_json({
            "type": "delegated_runs",
            "devcontainer_id": dc_id,
            "items": [{
                "run_id": "run-1", "harness": "codex", "model": "m",
                "status": "running", "result": None, "error": None,
                "started_at": "2026-06-20T00:00:00+00:00",
            }],
        })
    # the frontend-facing endpoint stays empty (FE↔BE deferred),
    # so assert persistence via the repository:
    from vibing_api.core.database import get_connection
    from vibing_api.repositories.delegated_runs import DelegatedRunRepository
    with get_connection() as conn:
        rows = DelegatedRunRepository(conn).list(dc_id)
    assert [r.run_id for r in rows] == ["run-1"]
```

Create `tests/api/test_harness_install_api.py` (mirror `tests/api/test_harnesses_api.py`'s command-dispatch assertion — a fake/connected runtime that records sent commands):

```python
def test_install_sends_install_command(client, connected_runtime):
    dc_id = connected_runtime.devcontainer_id  # adapt to this file's existing helper
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/harnesses/codex/install")
    assert resp.status_code == 202
    sent = connected_runtime.last_command
    assert sent.type.value == "install_harness"
    assert sent.payload == {"harness": "codex"}


def test_install_409_when_no_runtime(client):
    created = client.post(
        "/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"}
    ).json()
    resp = client.post(f"/api/v1/devcontainers/{created['id']}/harnesses/codex/install")
    assert resp.status_code == 409
```

(If `test_harnesses_api.py` uses a different mechanism to assert the dispatched command, reuse that exact mechanism here rather than inventing `connected_runtime`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/api/test_delegated_runs_repository.py tests/api/test_delegated_runs_channel.py tests/api/test_harness_install_api.py -v`
Expected: FAIL (missing table/repo/route).

- [ ] **Step 3: Add the table + bump schema version**

In `src/vibing_api/core/schema.py`: set `SCHEMA_VERSION = "7"`, add to `_TABLE_STATEMENTS`:

```python
    """
    CREATE TABLE IF NOT EXISTS delegated_runs (
        devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
        run_id TEXT NOT NULL,
        harness TEXT NOT NULL,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        result TEXT,
        error TEXT,
        started_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (devcontainer_id, run_id)
    )
    """,
```

And to `_INDEX_STATEMENTS`:

```python
    "CREATE INDEX IF NOT EXISTS idx_delegated_runs_devcontainer ON delegated_runs(devcontainer_id)",
```

- [ ] **Step 4: Create the repository**

Create `src/vibing_api/repositories/delegated_runs.py` (mirror `harness_status.py`; `error` is JSON-encoded):

```python
"""Delegated-run projection persistence. Repository executes; caller commits."""

import json
import sqlite3
from datetime import datetime, timezone

from pydantic import BaseModel
from vibing_protocol import DelegatedRunItem


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DelegatedRunRow(BaseModel):
    run_id: str
    harness: str
    model: str
    status: str
    result: str | None = None
    error: dict | None = None
    started_at: str


class DelegatedRunRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def replace(self, devcontainer_id: str, items: list[DelegatedRunItem]) -> None:
        self._conn.execute(
            "DELETE FROM delegated_runs WHERE devcontainer_id = ?", (devcontainer_id,)
        )
        now = _now()
        self._conn.executemany(
            "INSERT INTO delegated_runs "
            "(devcontainer_id, run_id, harness, model, status, result, error, started_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    devcontainer_id, it.run_id, it.harness, it.model, it.status,
                    it.result, json.dumps(it.error) if it.error is not None else None,
                    it.started_at, now,
                )
                for it in items
            ],
        )

    def list(self, devcontainer_id: str) -> list[DelegatedRunRow]:
        rows = self._conn.execute(
            "SELECT run_id, harness, model, status, result, error, started_at "
            "FROM delegated_runs WHERE devcontainer_id = ? ORDER BY run_id",
            (devcontainer_id,),
        ).fetchall()
        return [
            DelegatedRunRow(
                run_id=r["run_id"], harness=r["harness"], model=r["model"], status=r["status"],
                result=r["result"], error=json.loads(r["error"]) if r["error"] else None,
                started_at=r["started_at"],
            )
            for r in rows
        ]
```

- [ ] **Step 5: Add the `delegated_runs` SSE scope**

In `src/vibing_api/core/broadcaster.py`, extend the `Scope` literal and the docstring's scope list:

```python
Scope = Literal["devcontainers", "runtime", "harnesses", "delegated_runs"]
```

- [ ] **Step 6: Add `persist_delegated_runs`**

In `src/vibing_api/core/runtime_channel.py`, add (mirroring `persist_harness_status`):

```python
def persist_delegated_runs(
    devcontainer_id: str,
    items: list,  # list[DelegatedRunItem]
    broadcaster: Broadcaster | None = None,
) -> None:
    from vibing_api.repositories.delegated_runs import DelegatedRunRepository

    with get_connection() as conn:
        DelegatedRunRepository(conn).replace(devcontainer_id, items)
        conn.commit()
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="delegated_runs", ids=[devcontainer_id]))
```

- [ ] **Step 7: Handle the envelope in the WebSocket loop**

In `src/vibing_api/api/routes/runtime.py`: import `DelegatedRunsEnvelope` and `persist_delegated_runs`, and add a branch in `_serve` alongside the `harness_status` handling (after the `unregister is None` guard, before/after the harness_status branch):

```python
            if msg_type == "delegated_runs":
                try:
                    runs_env = DelegatedRunsEnvelope.model_validate(message)
                except ValidationError:
                    continue
                broadcaster = getattr(websocket.app.state, "broadcaster", None)
                try:
                    persist_delegated_runs(runs_env.devcontainer_id, runs_env.items, broadcaster)
                except Exception:
                    logger.exception(
                        "Failed to persist delegated runs (devcontainer=%s)",
                        runs_env.devcontainer_id,
                    )
                continue
```

Adjust the existing `if unregister is None or msg_type != "harness_status": continue` so it doesn't swallow `delegated_runs` — restructure the post-register dispatch to handle both message types explicitly (guard `unregister is None` once, then branch on `msg_type`).

- [ ] **Step 8: Add the install HTTP endpoint**

In `src/vibing_api/api/routes/harnesses.py`, add below `authenticate_harness` (note: this path is also what the frontend Install button calls — backing it is the intended side effect; no frontend code changes):

```python
@router.post(
    "/{devcontainer_id}/harnesses/{name}/install",
    status_code=status.HTTP_202_ACCEPTED,
)
async def install_harness(devcontainer_id: str, name: str, request: Request) -> dict:
    runtime_manager: RuntimeRegistry = request.app.state.runtime_manager
    if not runtime_manager.is_connected(devcontainer_id):
        raise RuntimeUnavailableError(f"No runtime connected for devcontainer {devcontainer_id!r}")
    command = Command(
        type=CommandType.INSTALL_HARNESS,
        devcontainer_id=devcontainer_id,
        payload={"harness": name},
    )
    await runtime_manager.send_command(devcontainer_id, command)
    return {}
```

- [ ] **Step 9: Add the CLI driver**

In `src/vibing_cli/client/harnesses.py`, add next to `authenticate`:

```python
@app.command("install")
def install(devcontainer_id: str, name: str, json_: JsonOption = False) -> None:
    """Trigger harness install."""
    render(
        request("POST", f"{_DC_BASE}/{devcontainer_id}/harnesses/{name}/install"),
        json_,
    )
```

- [ ] **Step 10: Run the new tests + full suite + checks**

Run: `uv run pytest tests/api/test_delegated_runs_repository.py tests/api/test_delegated_runs_channel.py tests/api/test_harness_install_api.py -v`
Expected: PASS.

Run: `uv run pytest -q && uv run mypy src && uv run ruff check src tests && uv run ruff format --check src tests`
Expected: all green/clean. (If a `schema_version`/migration test pins `"6"`, update it to `"7"`.)

- [ ] **Step 11: Commit**

```bash
git add src/vibing_api src/vibing_cli tests/api
git commit -m "feat(api): persist delegated-run snapshots + install_harness endpoint and CLI"
```

---

### Task 8: Dev-loop integration gate (UI → API → `devcontainer up`; unit-verify the bridges)

Verify the wired layers in the fast dev loop up to a real `devcontainer up` reaching `running`, and confirm the new bridges via their automated suites. The runtime→backend WebSocket hop is **not** expected to work here (the dev container does not publish `:8080` on the host); the full round trip is the prod gate (Task 9).

**Files:** none (verification + local tooling).
**Interfaces:** Consumes Tasks 1–7.

- [ ] **Step 1: Confirm dev-loop tooling**

Run: `node --version && docker version --format '{{.Server.Version}}' && uv --version`
Expected: all print; docker **Server** version proves the host daemon is reachable.

Run: `devcontainer --version || npm install -g @devcontainers/cli`
Expected: a version prints (installing if absent).

- [ ] **Step 2: Build the injection wheel where the injector looks**

Run: `sudo mkdir -p /opt/vibing/wheels && sudo chown "$(id -u):$(id -g)" /opt/vibing/wheels && uv build --wheel --out-dir /opt/vibing/wheels`
Expected: a `vibing-*.whl` appears in `/opt/vibing/wheels`.

- [ ] **Step 3: Start the backend (terminal A)**

Run: `uv run uvicorn vibing_api.main:app --host 0.0.0.0 --port 8080`
Expected: Uvicorn on `:8080`; `init_db()` runs (schema v7).

Verify (terminal C): `curl -fsS http://localhost:8080/api/v1/health`
Expected: 200 health JSON.

- [ ] **Step 4: Start the frontend (terminal B) and confirm the proxy**

Run: `cd apps/web && pnpm dev` (NOT `dev:mock` — we want the real backend).
Then: `curl -fsS http://localhost:5173/api/v1/health`
Expected: the same 200 JSON (proves Task 1).

- [ ] **Step 5: Confirm the empty delegated-runs endpoint through the proxy**

Create a devcontainer (UI or curl), then:
Run: `curl -fsS http://localhost:5173/api/v1/devcontainers/<id>/delegated-runs`
Expected: `{"items":[]}`; the detail page's RailActivity shows its empty state, no error card.

- [ ] **Step 6: Exercise the lifecycle from the UI**

In the UI: Add devcontainer with `local_path` = a folder visible to the host daemon at that identical absolute path, containing `.devcontainer/` (start from `devcontainer_examples/sandbox`) → Start.
Expected: status badge animates `created → starting → running` over SSE.
Confirm: `curl -fsS http://localhost:8080/api/v1/devcontainers/<id> | python -m json.tool` shows `running`.

- [ ] **Step 7: Diagnose lifecycle breakages (expected on first real run)**

For each failure read backend logs + the error status:
- **path not a dir / `up` fails immediately** → `local_path` not visible to the host daemon at that absolute path. Use a host-visible identical path (prod compose mounts `PROJECTS_DIR` identically for this reason).
- **`devcontainer: command not found`** → re-run Step 1's install.
- **docker permission denied** → confirm `docker ps` works in this terminal.
- **injection warnings after `running`** → expected here; the runtime can't reach `:8080` (not host-published). Deferred to Task 9.
Fix, retry Step 6 until `running`; then Stop from the UI → `stopping → stopped`.

- [ ] **Step 8: Unit-verify the backend↔runtime bridges**

Run: `uv run pytest tests/devcontainer_runtime tests/protocol tests/api/test_delegated_runs_channel.py tests/api/test_harness_install_api.py -q`
Expected: green — confirms install command + delegated-run snapshot persistence end-to-end at the unit/integration level.

- [ ] **Step 9: Full suites**

Run: `uv run pytest -q` and `cd apps/web && pnpm test`
Expected: both green.

- [ ] **Step 10: Commit any integration fixes**

```bash
git add -A && git commit -m "fix: dev-loop integration fixes for end-to-end lifecycle"
```

(Skip if Step 7 needed no code changes.)

---

### Task 9: Production-image gate (full round trip: runtime connect, authenticate, install, delegated-run report)

Run the real topology via `scripts/start.sh` and drive the served UI + CLI to prove the whole slice, including the runtime→CP hops added in Tasks 6–7.

**Files:** none (verification).
**Interfaces:** Consumes Tasks 1–8 (all committed, so the built image includes them).

- [ ] **Step 1: Provide a host projects dir with a real devcontainer target**

Run: `export PROJECTS_DIR=/abs/host/path/to/projects`
Expected: exists on the host, contains a project with `.devcontainer/devcontainer.json` (copy `devcontainer_examples/sandbox` in if needed).

- [ ] **Step 2: Build + run the production image**

Run: `scripts/start.sh` (or `docker compose up --build` if you need the compose-wired `PROJECTS_DIR`/identical-path/socket mounts).
Expected: builds (frontend + backend + wheel into `/opt/vibing/wheels`), starts, health passes, prints `Vibing is running at http://localhost:8080`.

- [ ] **Step 3: Store a managed-harness credential via the CLI**

Run: `uv run vibing --api-url http://localhost:8080 harness creds set codex --blob '{"OPENAI_API_KEY":"sk-..."}'`
Expected: `✓ Credentials set for codex.` (Verify: `curl -fsS http://localhost:8080/api/v1/settings/harness-credentials` lists `codex`.)

- [ ] **Step 4: Create + start a devcontainer from the served UI**

Open `http://localhost:8080`. Add a devcontainer with `local_path` under `PROJECTS_DIR` → Start.
Expected: `created → starting → running`; backend then injects + launches the runtime.

- [ ] **Step 5: Verify the runtime connects + reports harness status**

On the detail page after `running`:
Expected: the runtime-connected dot lights; the harness panel populates from real Harness Status (`codex` shows `installed`, `authenticated` per credential validity).
If the dot never lights, read the runtime log: `docker exec vibing sh -c 'docker exec <devcontainer> cat /tmp/vibing-agent.log'`. Common causes: `host.docker.internal:8080` not reachable (check `runtime_injector_url.py` gateway resolution); injection step failed (backend logs).

- [ ] **Step 6: Exercise install + authenticate from CLI/UI**

Run: `uv run vibing --api-url http://localhost:8080 harness install <devcontainer-id> cursor`
Expected: 202; the runtime installs `cursor` on demand and reports `harness_status`; the harness panel updates over SSE (`cursor` flips to `installed`).

Then click **Authenticate** on `codex` in the UI.
Expected: 202; the runtime writes the credential, re-checks, reports status; panel updates.

- [ ] **Step 7: Verify the delegated-run snapshot reaches the CP store**

Trigger a Delegated Run from inside the container via the runtime MCP server (the main harness's normal path; or call the MCP `spawn` tool directly against `http://127.0.0.1:8848` inside the container). Then confirm the CP stored the snapshot (the frontend GET stays empty by design, so check the store):

Run: `docker exec vibing sh -c "sqlite3 /data/vibing.db 'SELECT run_id,status FROM delegated_runs;'"`
Expected: at least one row reflecting the run's latest state (proves the runtime→CP delegated-run bridge). The frontend RailActivity still shows empty (FE↔BE deferred) — confirm it does not error.

- [ ] **Step 8: Confirm the Install button now succeeds (intended side effect)**

On a not-installed harness row in the UI, click **Install**.
Expected: it triggers the real install path (no 404). Page stays usable.

- [ ] **Step 9: Record outcome + tear down**

Capture the working slice (notes/screenshot): create → start → runtime connect → authenticate/install → harness + delegated-run state in the CP. Then `scripts/start.sh --stop`.

- [ ] **Step 10: Final full-suite check**

Run: `uv run pytest -q` and `cd apps/web && pnpm test`
Expected: both green.

---

## Self-Review

**Spec coverage:**
- Real e2e vertical slice (create → start → runtime connect → credential → authenticate → status to UI) → Task 9 Steps 3–6.
- Dev loop + prod gate → Tasks 8, 9.
- Wire-only, delete nothing; Install button intact → Global Constraints; Task 9 Step 8.
- Empty delegated-runs FE stub → Task 2 (stays empty; Task 7 Step 4 note + Task 9 Step 7 confirm the deferral).
- **Bridge backend↔runtime, not frontend↔backend** → install: Tasks 5/6/7 add Command + handler + endpoint + CLI, frontend untouched; delegated runs: Tasks 5/6/7 add envelope + runtime push + CP storage, GET stays empty.
- Amend ADR-0015 + CONTEXT coherence → Task 4.
- Snapshot (not delta) reporting → Task 6 Step 5; rationale in ADR-0016 (Task 4).
- Credentials via CLI (host login not built) → Task 9 Step 3.
- Out-of-scope (host-login capture, FE wiring of stored runs, runtime/diagnostics detection, Settings Preferences) → untouched.

**Placeholder scan:** No TBD/TODO. Verification tasks (8, 9) give exact commands + expected output + concrete likely-cause/fix guidance — appropriate for first-run integration. Test steps that reuse existing fixtures explicitly say "reuse this file's existing helper" rather than inventing parallel scaffolding; implementers must wire to the real fixture names found in those files.

**Type consistency:**
- `DelegatedRunItem`/`DelegatedRunsEnvelope` (Task 5) shape (`run_id, harness, model, status, result: str|None, error: dict|None, started_at`) is identical across protocol (5), runtime `list_runs()` (6), CP repo `DelegatedRunRow`/`replace` (7), API schema (2), and frontend `DelegatedRun`.
- `CommandType.INSTALL_HARNESS` wire value `"install_harness"` consistent across Tasks 5–7 and CONTEXT (4).
- `persist_delegated_runs(devcontainer_id, items, broadcaster=None)` (Task 7 Step 6) matches its call site in `runtime.py` (Step 7).
- New SSE scope `"delegated_runs"` (Task 7 Step 5) matches the frontend's registered scope and `persist_delegated_runs`'s publish.
- `DelegatedRunManager.report` hook + `list_runs()` (Task 6) match the CLI wiring (Task 6 Step 7).
- Schema bump `"6"`→`"7"` (Task 7 Step 3) flagged for the migration test (Step 10).
