# Runtime Lifecycle Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Devcontainer Runtime a user-driven, Control-Plane-observed lifecycle (`connected`/`launching`/`disconnected`) with stop + on-demand log retrieval, and fix the injector so bootstrap failures are no longer silent.

**Architecture:** The launch stays **detached** — the WebSocket remains the durable liveness truth. A new `RuntimeState` enum is resolved like devcontainer `status` (durable WS truth + an in-memory `launching` transient cleared by WS-connect or a timeout). The injector is fixed to run `uv tool install` **synchronously** (so bootstrap failures return through `RunResult`), unify all output into one in-container log, and write a PID file; stop is `docker exec` kill via that PID file; logs are `docker exec cat` on demand. A new `RuntimeService` owns the launching/timeout orchestration, stop, and log retrieval. See ADR-0017.

**Tech Stack:** Python 3.13, FastAPI, asyncio, pytest (backend); React + TypeScript + Vite + Tailwind, vitest, MSW, Playwright (frontend).

## Global Constraints

- Python checks must pass: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Frontend checks must pass: `pnpm test`, `pnpm build` (tsc), `pnpm e2e` (run from `apps/web`).
- All backend access from the frontend goes through `src/lib/api/` — never `fetch` directly. New API call ⇒ update `endpoints.ts` + `types.ts` + Control Plane API Mocking (`handlers.ts`, mock `state/`) in the same change.
- DTO types in `apps/web/src/lib/api/types.ts` must stay in sync with the backend Pydantic schemas.
- Domain language is canonical (`CONTEXT.md`): "Devcontainer Runtime" (never "agent"), "Control Plane", runtime states `connected`/`launching`/`disconnected`.
- Prefer self-explanatory code over comments; comment only the non-obvious. Minimum code that solves the problem.
- The runtime is launched via `devcontainer exec`; stop/log retrieval use `<engine> exec <container_id>` (engine defaults to `docker`).
- In-container paths (constants): log = `/tmp/vibing-runtime.log`, pid = `/tmp/vibing-runtime.pid`. These replace the old `/tmp/vibing-agent.log`.

---

## File Structure

**Phase A — Backend (`src/vibing_api`, independently shippable + testable)**

- Create `src/vibing_api/core/runtime_status_resolver.py` — pure `resolve_runtime_state(transient, connected)`.
- Create `src/vibing_api/core/runtime_service.py` — `RuntimeService`: inject (launching + timeout), stop, logs orchestration.
- Modify `src/vibing_api/core/vocabularies.py` — add `RuntimeState` enum.
- Modify `src/vibing_api/core/live_state.py` — add runtime-transient map + accessors.
- Modify `src/vibing_api/core/runtime_injector.py` — fix bash payload (sync install, tee to one log, pidfile, detach only runtime); `inject`/`inject_by_path` return `bool`; add `stop_runtime` + `read_log`.
- Modify `src/vibing_api/api/schemas/devcontainers.py` — `RuntimeConnection.state: RuntimeState` (replaces `runtime_connected`).
- Modify `src/vibing_api/api/routes/devcontainers.py` — resolve runtime state in `_view`; route inject through `RuntimeService`; add `stop-runtime` + `runtime-logs` endpoints.
- Modify `src/vibing_api/api/routes/runtime.py` — clear the launching transient on register.
- Modify `src/vibing_api/main.py` — wire `RuntimeService` into `app.state`.
- Modify `src/vibing_api/CLAUDE.md`, `src/vibing_devcontainer_runtime/CLAUDE.md` — doc coherence.

**Phase B — Frontend (`apps/web`)**

- Modify `apps/web/src/lib/api/types.ts` — `RuntimeState` type; `RuntimeConnection.state`.
- Modify `apps/web/src/lib/api/endpoints.ts` — `stopRuntime`, `fetchRuntimeLogs`.
- Modify `apps/web/src/mock/state/devcontainers.ts` + `apps/web/src/mock/handlers.ts` — `state` field; `stop-runtime` + `runtime-logs` handlers.
- Modify `apps/web/src/routes/DevcontainerDetail.tsx` — three-state RuntimeSection + Stop + View logs.
- Modify `apps/web/src/routes/Devcontainers.tsx` — list badge uses `state === 'connected'`.
- Update tests: `apps/web/src/routes/DevcontainerDetail.test.tsx`, `apps/web/src/mock/state/__tests__/devcontainers.test.ts`, `apps/web/src/routes/__tests__/Devcontainers.test.tsx`, `apps/web/e2e/devcontainer-detail.spec.ts`.
- Modify `apps/web/CLAUDE.md` — doc coherence.

---

## Phase A — Backend

### Task A1: RuntimeState enum, live-state transient, and resolver

**Files:**
- Modify: `src/vibing_api/core/vocabularies.py`
- Modify: `src/vibing_api/core/live_state.py:20-42`
- Create: `src/vibing_api/core/runtime_status_resolver.py`
- Test: `tests/api/test_runtime_status_resolver.py` (create), `tests/api/test_live_state.py` (extend)

**Interfaces:**
- Produces: `RuntimeState` enum with members `CONNECTED`, `LAUNCHING`, `DISCONNECTED` (StrEnum → values `"connected"`, `"launching"`, `"disconnected"`).
- Produces: `LiveStateStore.set_runtime_transient(id, RuntimeState)`, `.clear_runtime_transient(id)`, `.get_runtime_transient(id) -> RuntimeState | None`.
- Produces: `resolve_runtime_state(transient: RuntimeState | None, connected: bool) -> RuntimeState`.

- [ ] **Step 1: Write the failing resolver test**

Create `tests/api/test_runtime_status_resolver.py`:

```python
from vibing_api.core.runtime_status_resolver import resolve_runtime_state
from vibing_api.core.vocabularies import RuntimeState


def test_connected_wins_over_launching() -> None:
    assert resolve_runtime_state(RuntimeState.LAUNCHING, True) == RuntimeState.CONNECTED


def test_connected_when_registry_connected() -> None:
    assert resolve_runtime_state(None, True) == RuntimeState.CONNECTED


def test_launching_when_transient_and_not_connected() -> None:
    assert resolve_runtime_state(RuntimeState.LAUNCHING, False) == RuntimeState.LAUNCHING


def test_disconnected_by_default() -> None:
    assert resolve_runtime_state(None, False) == RuntimeState.DISCONNECTED
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/api/test_runtime_status_resolver.py -q`
Expected: FAIL — `ImportError` (`RuntimeState` / `resolve_runtime_state` not defined).

- [ ] **Step 3: Add the `RuntimeState` enum**

In `src/vibing_api/core/vocabularies.py`, append:

```python
class RuntimeState(StrEnum):
    CONNECTED = auto()
    LAUNCHING = auto()
    DISCONNECTED = auto()
```

- [ ] **Step 4: Create the resolver**

Create `src/vibing_api/core/runtime_status_resolver.py`:

```python
"""Live runtime state: WS-connected is the durable truth, launching is transient."""

from vibing_api.core.vocabularies import RuntimeState


def resolve_runtime_state(transient: RuntimeState | None, connected: bool) -> RuntimeState:
    if connected:
        return RuntimeState.CONNECTED
    if transient == RuntimeState.LAUNCHING:
        return RuntimeState.LAUNCHING
    return RuntimeState.DISCONNECTED
```

- [ ] **Step 5: Add the runtime-transient map to `LiveStateStore`**

In `src/vibing_api/core/live_state.py`, import the enum (already imports `DevcontainerStatus`):

```python
from vibing_api.core.vocabularies import DevcontainerStatus, RuntimeState
```

In `__init__`, add a third map:

```python
        self._runtime_transient: dict[str, RuntimeState] = {}
```

Add accessors (place after the `get_transient` method):

```python
    def set_runtime_transient(self, devcontainer_id: str, state: RuntimeState) -> None:
        self._runtime_transient[devcontainer_id] = state

    def clear_runtime_transient(self, devcontainer_id: str) -> None:
        self._runtime_transient.pop(devcontainer_id, None)

    def get_runtime_transient(self, devcontainer_id: str) -> RuntimeState | None:
        return self._runtime_transient.get(devcontainer_id)
```

- [ ] **Step 6: Add a live-state test for the runtime transient**

Append to `tests/api/test_live_state.py`:

```python
def test_runtime_transient_set_get_clear() -> None:
    from vibing_api.core.live_state import LiveStateStore
    from vibing_api.core.vocabularies import RuntimeState

    store = LiveStateStore()
    assert store.get_runtime_transient("dc1") is None
    store.set_runtime_transient("dc1", RuntimeState.LAUNCHING)
    assert store.get_runtime_transient("dc1") == RuntimeState.LAUNCHING
    store.clear_runtime_transient("dc1")
    assert store.get_runtime_transient("dc1") is None
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/api/test_runtime_status_resolver.py tests/api/test_live_state.py -q`
Expected: PASS.

- [ ] **Step 8: Lint, format, type-check**

Run: `uv run ruff check src tests && uv run ruff format src tests && uv run mypy src`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add src/vibing_api/core/vocabularies.py src/vibing_api/core/live_state.py src/vibing_api/core/runtime_status_resolver.py tests/api/test_runtime_status_resolver.py tests/api/test_live_state.py
git commit -m "feat(api): RuntimeState enum, runtime transient, and resolver"
```

---

### Task A2: Fix the injector — synchronous install, unified log, PID file, stop/read-log

**Files:**
- Modify: `src/vibing_api/core/runtime_injector.py`
- Test: `tests/api/test_runtime_injector.py`

**Interfaces:**
- Consumes: `RunResult` (`vibing_api.core.devcontainer_cli`), `Runner` callable.
- Produces: `RuntimeInjector.inject(devcontainer_id, container_id, local_path) -> bool` (True = runtime launched / bootstrap ok; False = a step failed).
- Produces: `RuntimeInjector.inject_by_path(devcontainer_id, local_path) -> bool`.
- Produces: `RuntimeInjector.stop_runtime(local_path) -> bool`.
- Produces: `RuntimeInjector.read_log(local_path) -> str | None`.
- Produces: module constants `CONTAINER_LOG_PATH = "/tmp/vibing-runtime.log"`, `CONTAINER_PID_PATH = "/tmp/vibing-runtime.pid"`.

- [ ] **Step 1: Write failing tests for the new bash payload and helpers**

Replace the body of `tests/api/test_runtime_injector.py` with:

```python
import asyncio
from pathlib import Path

from vibing_api.core.devcontainer_cli import RunResult
from vibing_api.core.runtime_injector import (
    CONTAINER_LOG_PATH,
    CONTAINER_PID_PATH,
    RuntimeInjector,
)


def _wheel_dir(tmp_path: Path) -> str:
    (tmp_path / "vibing-0.1.0-py3-none-any.whl").write_text("")
    return str(tmp_path)


def test_inject_by_path_resolves_container_then_injects(tmp_path: Path) -> None:
    calls = []

    async def runner(command):
        calls.append(command)
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir=_wheel_dir(tmp_path))
    ok = asyncio.run(injector.inject_by_path("dc1", "/work/repo"))
    assert ok is True
    assert any(
        c[:3] == ["docker", "ps", "-q"] and "label=devcontainer.local_folder=/work/repo" in c
        for c in calls
    )


def test_inject_payload_installs_synchronously_and_detaches_only_runtime(tmp_path: Path) -> None:
    payloads = []

    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[:2] == ["devcontainer", "exec"]:
            payloads.append(command[-1])
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir=_wheel_dir(tmp_path))
    asyncio.run(injector.inject_by_path("dc1", "/work/repo"))
    assert len(payloads) == 1
    payload = payloads[0]
    # install runs synchronously (not backgrounded) and tees into the unified log
    assert "set -e" in payload and "pipefail" in payload
    assert f"tee {CONTAINER_LOG_PATH}" in payload
    # only the long-running runtime is detached, and its PID is recorded
    assert "nohup vibing runtime devcontainer" in payload
    assert f"echo $! >{CONTAINER_PID_PATH}" in payload
    # the whole chain is NOT backgrounded (no trailing "&" on the install/export)
    assert "vibing &" not in payload


def test_inject_returns_false_when_a_step_fails(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[0] == "docker" and command[1] == "cp":
            return RunResult(1, "", "no such file")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir=_wheel_dir(tmp_path))
    assert asyncio.run(injector.inject_by_path("dc1", "/work/repo")) is False


def test_stop_runtime_kills_via_pid_file(tmp_path: Path) -> None:
    calls = []

    async def runner(command):
        calls.append(command)
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner)
    ok = asyncio.run(injector.stop_runtime("/work/repo"))
    assert ok is True
    exec_calls = [c for c in calls if c[:2] == ["docker", "exec"]]
    assert exec_calls and CONTAINER_PID_PATH in exec_calls[0][-1]


def test_read_log_returns_container_file_contents(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[:2] == ["docker", "exec"]:
            return RunResult(0, "install ok\nruntime started\n", "")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner)
    log = asyncio.run(injector.read_log("/work/repo"))
    assert log == "install ok\nruntime started\n"


def test_read_log_returns_none_when_no_container(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "\n", "")  # no container id
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner)
    assert asyncio.run(injector.read_log("/work/repo")) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_runtime_injector.py -q`
Expected: FAIL — `ImportError` for `CONTAINER_LOG_PATH` / missing `stop_runtime` / `read_log`, and payload assertions fail.

- [ ] **Step 3: Rewrite the injector module**

In `src/vibing_api/core/runtime_injector.py`:

Replace the module docstring + constants block (lines 1-20) with:

```python
"""Injects the Devcontainer Runtime into a running container, and controls it.

Copies uv + vibing wheel via docker cp, then runs a single devcontainer exec that
installs the runtime synchronously (so bootstrap failures surface via the exec's
exit code and are teed into the unified log), then detaches ONLY the long-running
runtime and records its PID. `stop_runtime` and `read_log` drive the container via
`<engine> exec`.

inject()/inject_by_path() return True when the runtime was launched (bootstrap ok),
False when any step failed (the failure is logged and lives in the unified log).
"""

from pathlib import Path

from logzero import logger

from vibing_api.core.runtime_injector_url import resolve_runtime_control_plane_url
from vibing_api.core.devcontainer_cli import Runner, _default_runner

_DEFAULT_UV_BINARY = "/usr/local/bin/uv"
_DEFAULT_WHEEL_DIR = "/opt/vibing/wheels"
_CONTAINER_UV_DEST = "/usr/local/bin/uv"
_CONTAINER_WHEEL_DIR = "/tmp"

CONTAINER_LOG_PATH = "/tmp/vibing-runtime.log"
CONTAINER_PID_PATH = "/tmp/vibing-runtime.pid"
```

Replace the `inject` method (current lines 41-87) with a version that returns `bool` and uses the fixed payload:

```python
    async def inject(self, devcontainer_id: str, container_id: str, local_path: str) -> bool:
        logger.info("runtime injection: %s into container %s", devcontainer_id, container_id)
        wheel = self._find_wheel()
        if wheel is None:
            logger.warning("Runtime injection skipped: no .whl found in %s", self._wheel_dir)
            return False

        container_wheel_path = f"{_CONTAINER_WHEEL_DIR}/{wheel.name}"

        if not await self._run(
            [self._engine, "cp", self._uv_binary, f"{container_id}:{_CONTAINER_UV_DEST}"],
            "cp uv binary",
            devcontainer_id,
        ):
            return False

        if not await self._run(
            [self._engine, "cp", str(wheel), f"{container_id}:{container_wheel_path}"],
            "cp wheel",
            devcontainer_id,
        ):
            return False

        agent_url = resolve_runtime_control_plane_url(self._runtime_url)
        bash_payload = (
            "set -e -o pipefail\n"
            f"{_CONTAINER_UV_DEST} tool install --python 3.13 --from {container_wheel_path} vibing"
            f" 2>&1 | tee {CONTAINER_LOG_PATH}\n"
            'export PATH="$HOME/.local/bin:$PATH"\n'
            f"nohup vibing runtime devcontainer"
            f" --control-plane-url {agent_url}"
            f" --devcontainer-id {devcontainer_id}"
            f" >>{CONTAINER_LOG_PATH} 2>&1 &\n"
            f"echo $! >{CONTAINER_PID_PATH}\n"
        )
        if await self._run(
            [
                self._cli,
                "exec",
                "--workspace-folder",
                local_path,
                "--",
                "bash",
                "-lc",
                bash_payload,
            ],
            "devcontainer exec",
            devcontainer_id,
        ):
            logger.info("runtime injection launched: %s (waiting for WS connect)", devcontainer_id)
            return True
        return False
```

Update `inject_by_path` (current lines 100-105) to return `bool`:

```python
    async def inject_by_path(self, devcontainer_id: str, local_path: str) -> bool:
        container_id = await self.resolve_container_id(local_path)
        if container_id is None:
            logger.warning("inject: no running container for %s (%s)", devcontainer_id, local_path)
            return False
        return await self.inject(devcontainer_id, container_id, local_path)
```

Add `stop_runtime` and `read_log` (place after `inject_by_path`):

```python
    async def stop_runtime(self, local_path: str) -> bool:
        container_id = await self.resolve_container_id(local_path)
        if container_id is None:
            return False
        kill = f'kill "$(cat {CONTAINER_PID_PATH})" 2>/dev/null || true'
        return await self._run(
            [self._engine, "exec", container_id, "bash", "-lc", kill],
            "stop runtime",
            local_path,
        )

    async def read_log(self, local_path: str) -> str | None:
        container_id = await self.resolve_container_id(local_path)
        if container_id is None:
            return None
        try:
            result = await self._runner([self._engine, "exec", container_id, "cat", CONTAINER_LOG_PATH])
        except FileNotFoundError:
            return None
        if result.returncode != 0:
            return None
        return result.stdout
```

Update `_run`'s failure log (current lines 122-129) to include stdout (install output is teed to stdout, not stderr):

```python
        if result.returncode != 0:
            logger.warning(
                "Runtime injection failed at '%s' for %s (exit %d):\nstdout: %s\nstderr: %s",
                step,
                devcontainer_id,
                result.returncode,
                result.stdout[-2000:],
                result.stderr[-2000:],
            )
            return False
```

- [ ] **Step 4: Run the injector tests**

Run: `uv run pytest tests/api/test_runtime_injector.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, format, type-check**

Run: `uv run ruff check src tests && uv run ruff format src tests && uv run mypy src`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/vibing_api/core/runtime_injector.py tests/api/test_runtime_injector.py
git commit -m "fix(api): injector installs synchronously, unifies log, writes PID; add stop/read-log"
```

---

### Task A3: RuntimeService — launching/timeout orchestration, stop, logs

**Files:**
- Create: `src/vibing_api/core/runtime_service.py`
- Modify: `src/vibing_api/main.py:33,65,80-84`
- Test: `tests/api/test_runtime_service.py` (create)

**Interfaces:**
- Consumes: `RuntimeInjector` (`inject_by_path`, `stop_runtime`, `read_log`), `LiveStateStore`, `RuntimeRegistry`, `Broadcaster`, `RuntimeState`, `run_in_background`.
- Produces: `RuntimeService(injector, *, live_state, registry, broadcaster=None, launch_timeout=30.0)`.
- Produces: `async inject(devcontainer_id, local_path) -> None`, `async stop(devcontainer_id, local_path) -> None`, `async read_log(local_path) -> str | None`, `async _expire_launching(devcontainer_id) -> None`.

- [ ] **Step 1: Write failing tests**

Create `tests/api/test_runtime_service.py`:

```python
import asyncio

from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.core.runtime_service import RuntimeService
from vibing_api.core.vocabularies import RuntimeState


class FakeInjector:
    def __init__(self, inject_ok: bool = True) -> None:
        self.inject_ok = inject_ok
        self.stopped: list[str] = []
        self.log = "log contents"

    async def inject_by_path(self, devcontainer_id: str, local_path: str) -> bool:
        return self.inject_ok

    async def stop_runtime(self, local_path: str) -> bool:
        self.stopped.append(local_path)
        return True

    async def read_log(self, local_path: str) -> str | None:
        return self.log


class FakeConn:
    async def send(self, command) -> None: ...


def _service(injector, registry=None, timeout=30.0):
    return RuntimeService(
        injector,
        live_state=LiveStateStore(),
        registry=registry or RuntimeRegistry(),
        broadcaster=None,
        launch_timeout=timeout,
    )


def test_inject_sets_launching_transient() -> None:
    svc = _service(FakeInjector(inject_ok=True), timeout=999)
    asyncio.run(svc.inject("dc1", "/work/repo"))
    assert svc._live.get_runtime_transient("dc1") == RuntimeState.LAUNCHING


def test_inject_failure_clears_to_disconnected() -> None:
    svc = _service(FakeInjector(inject_ok=False))
    asyncio.run(svc.inject("dc1", "/work/repo"))
    assert svc._live.get_runtime_transient("dc1") is None


def test_expire_launching_clears_when_not_connected() -> None:
    svc = _service(FakeInjector(), timeout=0)
    svc._live.set_runtime_transient("dc1", RuntimeState.LAUNCHING)
    asyncio.run(svc._expire_launching("dc1"))
    assert svc._live.get_runtime_transient("dc1") is None


def test_expire_launching_noop_when_connected() -> None:
    registry = RuntimeRegistry()
    registry.register("dc1", FakeConn())
    svc = _service(FakeInjector(), registry=registry, timeout=0)
    svc._live.set_runtime_transient("dc1", RuntimeState.LAUNCHING)
    asyncio.run(svc._expire_launching("dc1"))
    # connected → leave transient untouched (resolver makes connected win anyway)
    assert svc._live.get_runtime_transient("dc1") == RuntimeState.LAUNCHING


def test_stop_kills_and_clears_transient() -> None:
    injector = FakeInjector()
    svc = _service(injector)
    svc._live.set_runtime_transient("dc1", RuntimeState.LAUNCHING)
    asyncio.run(svc.stop("dc1", "/work/repo"))
    assert injector.stopped == ["/work/repo"]
    assert svc._live.get_runtime_transient("dc1") is None


def test_read_log_delegates_to_injector() -> None:
    svc = _service(FakeInjector())
    assert asyncio.run(svc.read_log("/work/repo")) == "log contents"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_runtime_service.py -q`
Expected: FAIL — `ModuleNotFoundError: vibing_api.core.runtime_service`.

- [ ] **Step 3: Create the service**

Create `src/vibing_api/core/runtime_service.py`:

```python
"""Runtime lifecycle orchestration (ADR-0017).

Owns the `launching` transient and its timeout, runtime stop, and on-demand log
retrieval. The WebSocket (RuntimeRegistry) is the durable liveness truth; this
service only manages the transient launching window and the control actions.
"""

import asyncio

from logzero import logger

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.devcontainer_service import run_in_background
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.core.runtime_injector import RuntimeInjector
from vibing_api.core.vocabularies import RuntimeState


class RuntimeService:
    def __init__(
        self,
        injector: RuntimeInjector,
        *,
        live_state: LiveStateStore,
        registry: RuntimeRegistry,
        broadcaster: Broadcaster | None = None,
        launch_timeout: float = 30.0,
    ) -> None:
        self._injector = injector
        self._live = live_state
        self._registry = registry
        self._broadcaster = broadcaster
        self._launch_timeout = launch_timeout

    def _publish(self, devcontainer_id: str) -> None:
        if self._broadcaster is not None:
            self._broadcaster.publish(SseEvent(scope="runtime", ids=[devcontainer_id]))

    async def inject(self, devcontainer_id: str, local_path: str) -> None:
        self._live.set_runtime_transient(devcontainer_id, RuntimeState.LAUNCHING)
        self._publish(devcontainer_id)
        launched = await self._injector.inject_by_path(devcontainer_id, local_path)
        if not launched:
            self._live.clear_runtime_transient(devcontainer_id)
            self._publish(devcontainer_id)
            return
        run_in_background(self._expire_launching(devcontainer_id))

    async def _expire_launching(self, devcontainer_id: str) -> None:
        await asyncio.sleep(self._launch_timeout)
        if self._registry.is_connected(devcontainer_id):
            return
        if self._live.get_runtime_transient(devcontainer_id) == RuntimeState.LAUNCHING:
            logger.info("runtime launch timed out: %s (-> disconnected)", devcontainer_id)
            self._live.clear_runtime_transient(devcontainer_id)
            self._publish(devcontainer_id)

    async def stop(self, devcontainer_id: str, local_path: str) -> None:
        await self._injector.stop_runtime(local_path)
        self._live.clear_runtime_transient(devcontainer_id)
        self._publish(devcontainer_id)

    async def read_log(self, local_path: str) -> str | None:
        return await self._injector.read_log(local_path)
```

- [ ] **Step 4: Wire it into the app factory**

In `src/vibing_api/main.py`, add the import after the `RuntimeInjector` import (line 33):

```python
from vibing_api.core.runtime_service import RuntimeService
```

After the `app.state.devcontainer_service = DevcontainerService(...)` block (ends line 84), add:

```python
    app.state.runtime_service = RuntimeService(
        app.state.runtime_injector,
        live_state=app.state.live_state,
        registry=app.state.runtime_manager,
        broadcaster=app.state.broadcaster,
    )
```

- [ ] **Step 5: Run the service tests**

Run: `uv run pytest tests/api/test_runtime_service.py -q`
Expected: PASS.

- [ ] **Step 6: Lint, format, type-check**

Run: `uv run ruff check src tests && uv run ruff format src tests && uv run mypy src`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/vibing_api/core/runtime_service.py src/vibing_api/main.py tests/api/test_runtime_service.py
git commit -m "feat(api): RuntimeService owns launching timeout, stop, and log retrieval"
```

---

### Task A4: API surface — `state` field, resolver in `_view`, stop-runtime + runtime-logs endpoints, clear-on-register

**Files:**
- Modify: `src/vibing_api/api/schemas/devcontainers.py:36-37`
- Modify: `src/vibing_api/api/routes/devcontainers.py` (imports, `_view`, inject route, new routes)
- Modify: `src/vibing_api/api/routes/runtime.py:103-114`
- Test: `tests/api/test_devcontainer_runtime_connection.py` (migrate to `state`), `tests/api/test_runtime_lifecycle_api.py` (create)

**Interfaces:**
- Consumes: `resolve_runtime_state` (A1), `RuntimeService` (A3), `RuntimeState` (A1).
- Produces: `RuntimeConnection { state: RuntimeState }` (replaces `runtime_connected: bool`).
- Produces: `RuntimeLogs { content: str | None }`.
- Produces: `POST /devcontainers/{id}/stop-runtime` (202), `GET /devcontainers/{id}/runtime-logs` (RuntimeLogs).

- [ ] **Step 1: Migrate the existing runtime-connection test to `state`, and add lifecycle API tests**

In `tests/api/test_devcontainer_runtime_connection.py`, replace every `["runtime"]["runtime_connected"] is False` with `["runtime"]["state"] == "disconnected"` and every `... is True` with `... == "connected"`. (8 assertions across list/detail/per-devcontainer tests.) Update the module docstring's `` `runtime_connected` field `` to `` `runtime.state` field ``.

Create `tests/api/test_runtime_lifecycle_api.py`:

```python
from fastapi.testclient import TestClient

AGENT_WS_URL = "/api/v1/runtime/agent/ws"


def _create(client: TestClient, name: str = "dc") -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": name, "local_path": f"/tmp/{name}"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_runtime_state_disconnected_by_default(client: TestClient) -> None:
    dc_id = _create(client)
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert body["runtime"]["state"] == "disconnected"


def test_runtime_state_connected_when_ws_open(client: TestClient) -> None:
    dc_id = _create(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json({"type": "runtime_registered", "devcontainer_id": dc_id})
        assert ws.receive_json() == {"type": "registered"}
        body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
        assert body["runtime"]["state"] == "connected"


def test_launching_transient_resolves_to_launching(client: TestClient) -> None:
    from vibing_api.core.vocabularies import RuntimeState

    dc_id = _create(client)
    client.app.state.live_state.set_runtime_transient(dc_id, RuntimeState.LAUNCHING)  # type: ignore[union-attr]
    body = client.get(f"/api/v1/devcontainers/{dc_id}").json()
    assert body["runtime"]["state"] == "launching"


def test_register_clears_launching_transient(client: TestClient) -> None:
    from vibing_api.core.vocabularies import RuntimeState

    dc_id = _create(client)
    client.app.state.live_state.set_runtime_transient(dc_id, RuntimeState.LAUNCHING)  # type: ignore[union-attr]
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json({"type": "runtime_registered", "devcontainer_id": dc_id})
        assert ws.receive_json() == {"type": "registered"}
        assert client.app.state.live_state.get_runtime_transient(dc_id) is None  # type: ignore[union-attr]


def test_stop_runtime_endpoint_returns_202(client: TestClient) -> None:
    dc_id = _create(client)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/stop-runtime")
    assert resp.status_code == 202


def test_runtime_logs_endpoint_returns_content(client: TestClient) -> None:
    dc_id = _create(client)

    async def fake_read_log(local_path: str) -> str | None:
        return "hello from the runtime"

    client.app.state.runtime_service.read_log = fake_read_log  # type: ignore[union-attr]
    body = client.get(f"/api/v1/devcontainers/{dc_id}/runtime-logs").json()
    assert body == {"content": "hello from the runtime"}


def test_stop_runtime_not_found(client: TestClient) -> None:
    resp = client.post("/api/v1/devcontainers/nope/stop-runtime")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_runtime_lifecycle_api.py tests/api/test_devcontainer_runtime_connection.py -q`
Expected: FAIL — `state` key missing (responses still carry `runtime_connected`); stop-runtime / runtime-logs routes 404 (not registered).

- [ ] **Step 3: Update the schema**

In `src/vibing_api/api/schemas/devcontainers.py`, add the import and replace `RuntimeConnection`, and add `RuntimeLogs`:

```python
from vibing_api.core.vocabularies import DevcontainerStatus, RuntimeState
```

```python
class RuntimeConnection(BaseModel):
    state: RuntimeState


class RuntimeLogs(BaseModel):
    content: str | None
```

- [ ] **Step 4: Resolve runtime state in `_view` and add the routes**

In `src/vibing_api/api/routes/devcontainers.py`:

Update imports — add `RuntimeLogs` to the schema import group, and add:

```python
from vibing_api.core.runtime_status_resolver import resolve_runtime_state
```

Replace the `runtime = RuntimeConnection(...)` block in `_view` (lines 34-36):

```python
    runtime = RuntimeConnection(
        state=resolve_runtime_state(
            live.get_runtime_transient(resolved.id),
            request.app.state.runtime_manager.is_connected(resolved.id),
        )
    )
```

Replace the `inject_runtime` route (lines 152-159) to go through `RuntimeService`, and append the two new routes:

```python
@router.post("/{devcontainer_id}/inject-runtime", status_code=202)
async def inject_runtime(devcontainer_id: str, request: Request) -> dict:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    service = request.app.state.runtime_service
    run_in_background(service.inject(resolved.id, resolved.local_path))
    return {}


@router.post("/{devcontainer_id}/stop-runtime", status_code=202)
async def stop_runtime(devcontainer_id: str, request: Request) -> dict:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    service = request.app.state.runtime_service
    run_in_background(service.stop(resolved.id, resolved.local_path))
    return {}


@router.get("/{devcontainer_id}/runtime-logs", response_model=RuntimeLogs)
async def runtime_logs(devcontainer_id: str, request: Request) -> RuntimeLogs:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    content = await request.app.state.runtime_service.read_log(resolved.local_path)
    return RuntimeLogs(content=content)
```

- [ ] **Step 5: Clear the launching transient on register**

In `src/vibing_api/api/routes/runtime.py`, inside `register()` after `_broadcast_connection(websocket, ids=[devcontainer_id])` (line 107), add:

```python
        websocket.app.state.live_state.clear_runtime_transient(devcontainer_id)
```

- [ ] **Step 6: Run the API tests**

Run: `uv run pytest tests/api/test_runtime_lifecycle_api.py tests/api/test_devcontainer_runtime_connection.py -q`
Expected: PASS.

- [ ] **Step 7: Run the full backend suite + checks**

Run: `uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`
Expected: PASS / no errors. (If any other test referenced `runtime_connected`, update it to `state` the same way.)

- [ ] **Step 8: Commit**

```bash
git add src/vibing_api/api/schemas/devcontainers.py src/vibing_api/api/routes/devcontainers.py src/vibing_api/api/routes/runtime.py tests/api/test_runtime_lifecycle_api.py tests/api/test_devcontainer_runtime_connection.py
git commit -m "feat(api): runtime.state enum + stop-runtime/runtime-logs endpoints"
```

---

### Task A5: Backend doc coherence

**Files:**
- Modify: `src/vibing_api/CLAUDE.md`
- Modify: `src/vibing_devcontainer_runtime/CLAUDE.md`

- [ ] **Step 1: Update `src/vibing_api/CLAUDE.md`**

In the `runtime_injector.py` bullet, replace its line with:

```markdown
  - `core/runtime_injector.py`: `docker cp` + synchronous `uv tool install` (teed to one in-container log `/tmp/vibing-runtime.log`) + detached launch of the runtime with its PID in `/tmp/vibing-runtime.pid`. `inject*` return `bool` (bootstrap ok). Also `stop_runtime` (`<engine> exec` kill via PID file) and `read_log` (`<engine> exec cat`, on demand).
  - `core/runtime_service.py`: `RuntimeService` — owns the `launching` transient + ~30s timeout, runtime `stop`, and on-demand `read_log`. WS connect is the durable truth; timeout/disconnect resolve to `disconnected`.
  - `core/runtime_status_resolver.py`: `resolve_runtime_state` — connected (WS) wins, else `launching` transient, else `disconnected`.
```

In the `devcontainers.py` route bullet, add after the `inject-runtime` sentence:

```markdown
 `POST /{id}/stop-runtime` (202, `docker exec` kill via PID file); `GET /{id}/runtime-logs` returns `{content}` (on-demand `docker exec cat`). The devcontainer view's `runtime` is `{state: connected|launching|disconnected}` (was `runtime_connected`).
```

In the `runtime.py` route bullet, add: `on register, clears the runtime `launching` transient.`

In `core/live_state.py` bullet, add: `plus a runtime-state transient (`launching`) cleared on WS connect / launch timeout.`

- [ ] **Step 2: Update `src/vibing_devcontainer_runtime/CLAUDE.md`**

In the `cli.py` line, note the unified log + PID file are written by the injector's launch wrapper (the runtime process itself is unchanged): append to the "Context" section a bullet:

```markdown
- Launched detached by the Control Plane's injector; its stdout/stderr (and the preceding `uv tool install`) are teed to `/tmp/vibing-runtime.log`, and its PID recorded in `/tmp/vibing-runtime.pid` for `stop-runtime`.
```

- [ ] **Step 3: Commit**

```bash
git add src/vibing_api/CLAUDE.md src/vibing_devcontainer_runtime/CLAUDE.md
git commit -m "docs(api): document runtime lifecycle, stop/logs, unified log + PID"
```

---

## Phase B — Frontend

### Task B1: API types + endpoint functions

**Files:**
- Modify: `apps/web/src/lib/api/types.ts:32-34`
- Modify: `apps/web/src/lib/api/endpoints.ts`

**Interfaces:**
- Produces: `type RuntimeState = 'connected' | 'launching' | 'disconnected'`; `RuntimeConnection { state: RuntimeState }`; `RuntimeLogs { content: string | null }`.
- Produces: `stopRuntime(id): Promise<void>`, `fetchRuntimeLogs(id): Promise<RuntimeLogs>`.

- [ ] **Step 1: Update `types.ts`**

Replace `RuntimeConnection` (lines 32-34) with:

```typescript
export type RuntimeState = 'connected' | 'launching' | 'disconnected'

export interface RuntimeConnection {
  state: RuntimeState
}

export interface RuntimeLogs {
  content: string | null
}
```

- [ ] **Step 2: Add endpoint functions**

In `apps/web/src/lib/api/endpoints.ts`, add `RuntimeLogs` to the type import list, and append after `injectRuntime`:

```typescript
export const stopRuntime = (id: string): Promise<void> =>
  sendJson<void>(`/devcontainers/${encodeURIComponent(id)}/stop-runtime`, 'POST')

export const fetchRuntimeLogs = (id: string): Promise<RuntimeLogs> =>
  getJson(`/devcontainers/${encodeURIComponent(id)}/runtime-logs`)
```

- [ ] **Step 3: Type-check**

Run (from `apps/web`): `pnpm build`
Expected: tsc fails — existing references to `runtime_connected` in `.tsx`/test files no longer compile. That is expected; those are fixed in B3. Proceed (the type change is correct).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/lib/api/endpoints.ts
git commit -m "feat(web): runtime.state type + stopRuntime/fetchRuntimeLogs endpoints"
```

---

### Task B2: Mock state + handlers

**Files:**
- Modify: `apps/web/src/mock/state/devcontainers.ts`
- Modify: `apps/web/src/mock/handlers.ts:145-157` (+ new handlers)
- Test: `apps/web/src/mock/state/__tests__/devcontainers.test.ts`

**Interfaces:**
- Consumes: `RuntimeState`, `RuntimeConnection` (B1).
- Produces: mock `stopRuntimeState(id)`; handlers for `POST .../stop-runtime` and `GET .../runtime-logs`.

- [ ] **Step 1: Update the mock-state tests**

In `apps/web/src/mock/state/__tests__/devcontainers.test.ts`:
- Line ~32: `expect(item.runtime).toHaveProperty('runtime_connected')` → `expect(item.runtime).toHaveProperty('state')`.
- Line ~42: `expect(dc.runtime).toEqual({ runtime_connected: true })` → `expect(dc.runtime).toEqual({ state: 'connected' })`.
- Line ~122: `...runtime.runtime_connected).toBe(false)` → `...runtime.state).toBe('disconnected')`.
- Line ~158: `...runtime.runtime_connected).toBe(false)` → `...runtime.state).toBe('disconnected')`.
- Lines ~182-184: rename test to `'sets state to connected on a known devcontainer'`; assert `...runtime.state).toBe('connected')`.

Add a test for the new stop helper (after the inject test):

```typescript
  it('stopRuntimeState disconnects the runtime and evicts harnesses', () => {
    injectRuntime('dc-seed-0002')
    expect(getDevcontainer('dc-seed-0002').runtime.state).toBe('connected')
    stopRuntimeState('dc-seed-0002')
    expect(getDevcontainer('dc-seed-0002').runtime.state).toBe('disconnected')
  })
```

Add `stopRuntimeState` to the import from `../devcontainers` at the top of the test file.

- [ ] **Step 2: Run to verify it fails**

Run (from `apps/web`): `pnpm test src/mock/state/__tests__/devcontainers.test.ts`
Expected: FAIL — `state` property missing; `stopRuntimeState` not exported.

- [ ] **Step 3: Update mock state**

In `apps/web/src/mock/state/devcontainers.ts`:

Replace the `SEED_RUNTIME` map (lines 6-11):

```typescript
const SEED_RUNTIME: Record<string, RuntimeConnection> = {
  'dc-seed-0001': { state: 'connected' },
  'dc-seed-0002': { state: 'disconnected' },
  'dc-seed-0003': { state: 'disconnected' },
  'dc-seed-0004': { state: 'disconnected' },
}
```

Replace every other `{ runtime_connected: false }` with `{ state: 'disconnected' }` (createDevcontainer line ~70, stopDevcontainer line ~95, removeContainer line ~109) and the inject line ~130 `{ runtime_connected: true }` with `{ state: 'connected' }`.

Add the stop helper after `injectRuntime`:

```typescript
// Stop the runtime: disconnect it and evict harness cache (mirrors backend stop-runtime).
export function stopRuntimeState(id: string): void {
  const idx = findIdx(id)
  store[idx] = { ...store[idx], runtime: { state: 'disconnected' }, updated_at: now() }
  evictHarnessEntry(id)
}
```

- [ ] **Step 4: Add the handlers**

In `apps/web/src/mock/handlers.ts`, after the `inject-runtime` handler (ends line 157), add:

```typescript
  http.post('*/api/v1/devcontainers/:id/stop-runtime', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      dc.stopRuntimeState(params.id as string)
      emitInvalidation('runtime')
      emitInvalidation('harnesses')
      return new HttpResponse(null, { status: 202 })
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
  }),

  http.get('*/api/v1/devcontainers/:id/runtime-logs', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      dc.getDevcontainer(params.id as string)
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
    return HttpResponse.json({ content: 'mock runtime log\ninstall ok\nruntime started\n' })
  }),
```

- [ ] **Step 5: Run the mock-state tests**

Run (from `apps/web`): `pnpm test src/mock/state/__tests__/devcontainers.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/mock/state/devcontainers.ts apps/web/src/mock/handlers.ts apps/web/src/mock/state/__tests__/devcontainers.test.ts
git commit -m "feat(web): mock runtime.state, stop-runtime + runtime-logs handlers"
```

---

### Task B3: RuntimeSection (three states + stop + view logs); list badge

**Files:**
- Modify: `apps/web/src/routes/DevcontainerDetail.tsx`
- Modify: `apps/web/src/routes/Devcontainers.tsx:127`
- Test: `apps/web/src/routes/DevcontainerDetail.test.tsx`, `apps/web/src/routes/__tests__/Devcontainers.test.tsx`

**Interfaces:**
- Consumes: `stopRuntime`, `fetchRuntimeLogs`, `RuntimeState` (B1).
- Produces: `ActionKind` includes `'stop-runtime'`; RuntimeSection renders one of three states, a Stop button when connected, an Inject button (greyed unless running), and a View-logs button opening a dialog.

- [ ] **Step 1: Update the detail tests**

In `apps/web/src/routes/DevcontainerDetail.test.tsx`:
- Line ~10: `runtime: { runtime_connected: true }` → `runtime: { state: 'connected' as const }`.
- Line ~46: `runtime: { runtime_connected: false }` → `runtime: { state: 'disconnected' as const }`.

Add tests (inside the existing describe block):

```typescript
  it('shows Connected with a Stop runtime button when connected', () => {
    renderDetail(base)  // base.runtime.state === 'connected'
    expect(screen.getByText('Connected')).toBeTruthy()
    expect(screen.getByTitle('Stop runtime')).toBeTruthy()
  })

  it('shows Launching when state is launching', () => {
    renderDetail({ ...base, runtime: { state: 'launching' as const } })
    expect(screen.getByText('Launching…')).toBeTruthy()
  })

  it('shows Disconnected when not connected', () => {
    renderDetail({ ...base, status: 'running' as const, runtime: { state: 'disconnected' as const } })
    expect(screen.getByText('Disconnected')).toBeTruthy()
  })
```

(`renderDetail` is the existing helper in this file that mounts the route with a given devcontainer fixture; reuse it exactly as the existing tests do. If the existing tests render via a different helper name, match that name.)

- [ ] **Step 2: Run to verify it fails**

Run (from `apps/web`): `pnpm test src/routes/DevcontainerDetail.test.tsx`
Expected: FAIL — `Connected`/`Launching…`/`Disconnected`/`Stop runtime` not found (component still keys off `runtime_connected`).

- [ ] **Step 3: Rewrite `RuntimeSection` and wiring in `DevcontainerDetail.tsx`**

Update imports (lines 8-19): add `StopIcon` is already imported; add a logs action. Extend the api import to include `stopRuntime, fetchRuntimeLogs`:

```typescript
import {
  fetchDevcontainer,
  startDevcontainer,
  stopDevcontainer,
  removeContainer,
  injectRuntime,
  stopRuntime,
  fetchRuntimeLogs,
  fetchHarnesses,
  useApiQuery,
  ApiError,
} from '../lib/api'
```

Change `ActionKind` (line 90):

```typescript
type ActionKind = 'start' | 'stop' | 'inject' | 'remove' | 'stop-runtime'
```

Replace `RuntimeSection` (lines 169-201) with:

```typescript
const RUNTIME_LABEL: Record<string, string> = {
  connected: 'Connected',
  launching: 'Launching…',
  disconnected: 'Disconnected',
}

export function RuntimeSection({
  dc,
  busy,
  onAction,
}: {
  dc: DevcontainerView
  busy: boolean
  onAction: (kind: ActionKind) => void
}) {
  const running = dc.status === 'running'
  const state = dc.runtime.state
  const connected = state === 'connected'
  const launching = state === 'launching'
  const [logs, setLogs] = useState<string | null>(null)
  const [showLogs, setShowLogs] = useState(false)

  async function viewLogs() {
    setShowLogs(true)
    const res = await fetchRuntimeLogs(dc.id)
    setLogs(res.content ?? '(no runtime log found)')
  }

  return (
    <section className="mb-5">
      <SectionTitle>Runtime</SectionTitle>
      <div className="flex items-center gap-2 text-[13px]">
        <span
          className={cn(
            'h-2 w-2 rounded-full',
            connected ? 'bg-ok' : launching ? 'bg-accent' : 'bg-text-subtle',
          )}
        />
        <span className={connected ? 'text-text' : 'text-text-muted'}>
          {RUNTIME_LABEL[state]}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <IconButton title="View runtime logs" busy={false} onClick={viewLogs}>
            <span className="text-[11px] font-medium">Logs</span>
          </IconButton>
          {connected ? (
            <IconButton title="Stop runtime" busy={busy} onClick={() => onAction('stop-runtime')}>
              <StopIcon />
            </IconButton>
          ) : (
            <IconButton
              title={running ? 'Inject runtime' : 'Start the container to inject runtime'}
              busy={busy && running}
              disabled={!running}
              onClick={() => onAction('inject')}
            >
              <InjectIcon />
            </IconButton>
          )}
        </div>
      </div>
      {showLogs && (
        <Dialog title="Runtime logs" onClose={() => setShowLogs(false)}>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-[12px] text-text-muted">
            {logs ?? 'Loading…'}
          </pre>
        </Dialog>
      )}
    </section>
  )
}
```

In `act()` (lines 254-268), add the stop-runtime branch (after the `inject` branch):

```typescript
      else if (kind === 'stop-runtime') await stopRuntime(dc.id)
```

- [ ] **Step 4: Update the list badge in `Devcontainers.tsx`**

At line 127, replace `{devcontainer.runtime.runtime_connected && (` with:

```typescript
              {devcontainer.runtime.state === 'connected' && (
```

In `apps/web/src/routes/__tests__/Devcontainers.test.tsx`:
- Line ~96: `runtime: { runtime_connected: false }` → `runtime: { state: 'disconnected' as const }`.
- Lines ~418-419: rename the test title's `runtime_connected` mention; `runtime: { runtime_connected: true }` → `runtime: { state: 'connected' as const }`.

- [ ] **Step 5: Run the frontend tests + build**

Run (from `apps/web`): `pnpm test && pnpm build`
Expected: PASS (vitest green; tsc clean — no remaining `runtime_connected` references).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/routes/DevcontainerDetail.tsx apps/web/src/routes/Devcontainers.tsx apps/web/src/routes/DevcontainerDetail.test.tsx apps/web/src/routes/__tests__/Devcontainers.test.tsx
git commit -m "feat(web): runtime section with connected/launching/disconnected, stop, view logs"
```

---

### Task B4: e2e + frontend doc coherence

**Files:**
- Modify: `apps/web/e2e/devcontainer-detail.spec.ts`
- Modify: `apps/web/CLAUDE.md`

- [ ] **Step 1: Update the e2e spec**

Open `apps/web/e2e/devcontainer-detail.spec.ts`. Where it asserts the runtime indicator / inject control, add assertions for the three-state model and the stop control. For the connected seed (`dc-seed-0001`), assert the section shows `Connected` and a `Stop runtime` button. For a stopped devcontainer, keep the existing disabled-inject assertion but update any visible-text expectation from `Not connected` to `Disconnected`. Add a check that clicking `Logs` opens a dialog titled `Runtime logs`:

```typescript
  test('runtime section: connected shows Stop and logs dialog', async ({ page }) => {
    await page.goto('/devcontainers/dc-seed-0001')
    await expect(page.getByText('Connected')).toBeVisible()
    await expect(page.getByTitle('Stop runtime')).toBeVisible()
    await page.getByTitle('View runtime logs').click()
    await expect(page.getByText('Runtime logs')).toBeVisible()
  })
```

(Match the spec's existing navigation/setup helpers and seed ids; adjust the route path if the spec uses a helper to open the detail view.)

- [ ] **Step 2: Run e2e**

Run (from `apps/web`): `pnpm e2e`
Expected: PASS.

- [ ] **Step 3: Update `apps/web/CLAUDE.md`**

In the detail-view paragraph (line 10), replace the runtime sentence:

```markdown
Runtime lives in its own "Runtime" section below (above Coding harnesses): a three-state indicator (`dc.runtime.state` — `connected` green / `launching` accent / `disconnected` grey), a "Logs" button that opens a dialog with on-demand `runtime-logs` content, and a control that is **Stop runtime** (`stop-runtime`) when connected or **Inject** (greyed/disabled unless the container is running) otherwise.
```

In the `src/mock/` line, update the scopes/endpoints note to add the new endpoints: `stop-runtime`, `runtime-logs`.

In the `src/lib/api/` note, nothing structural changes, but ensure no stale `runtime_connected` mention remains (search the file).

- [ ] **Step 4: Commit**

```bash
git add apps/web/e2e/devcontainer-detail.spec.ts apps/web/CLAUDE.md
git commit -m "test(web): e2e for runtime states + logs dialog; docs coherence"
```

---

## Self-Review

**Spec coverage (against ADR-0017 + grilling decisions):**
- Detached launch kept; WS durable truth → A1 resolver (connected wins), A4 `_view`. ✓
- No supervisord / no auto-restart → nothing added; A5/CONTEXT note it. ✓
- Three states `connected`/`launching`/`disconnected` → A1 enum, A4 schema, B1 type, B3 UI. ✓
- `launching` transient + ~30s timeout, cleared by WS-connect or timeout → A3 `RuntimeService`, A4 register-clears. ✓
- Explicit injection (no auto post-`up`) → unchanged behavior; CONTEXT/ADR-0014 already reconciled. ✓
- Stop = `docker exec` kill via PID file → A2 `stop_runtime`, A3/A4 `stop`. ✓
- No dedicated restart endpoint → not added (UI sequences stop then inject). ✓
- Bootstrap failures synchronous + backgrounding bug fixed + unified log → A2 payload + `inject` returns bool + `_run` logs stdout. ✓
- Logs on demand only (no speculative exec on timeout) → A2 `read_log`, A4 `runtime-logs` GET, B3 dialog; timeout path never reads logs. ✓
- `runtime.state` replaces `runtime_connected` → A4 schema + all FE references migrated (B1/B2/B3). ✓

**Placeholder scan:** No TBD/“handle edge cases”/“similar to Task N”; every code step shows full code. ✓

**Type consistency:** `RuntimeState` values `connected|launching|disconnected` identical in Python StrEnum (A1) and TS union (B1). `RuntimeConnection.state`, `RuntimeLogs.content` match across Pydantic (A4) and TS (B1). `inject_by_path -> bool` (A2) consumed by `RuntimeService.inject` (A3). `stop_runtime`/`read_log` signatures (A2) match `RuntimeService` calls (A3) and route usage (A4). `stopRuntime`/`fetchRuntimeLogs` (B1) consumed in B3. ✓

**Note on scope:** Phase A is independently shippable (backend API + tests green on its own). Phase B depends on Phase A's `state` field. Land A before B.
```
