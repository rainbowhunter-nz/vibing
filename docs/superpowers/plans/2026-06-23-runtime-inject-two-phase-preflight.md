# Two-phase Runtime Inject (bootstrap+preflight → spawn) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `RuntimeInjector.inject()` so the runtime is spawned only after bootstrap succeeds and a preflight HTTP health probe confirms the control plane is reachable from inside the container.

**Architecture:** A new in-container `vibing runtime preflight` command GETs the control plane's `/api/v1/health` (derived from the same resolved WS URL the runtime uses). `inject()` runs a `_bootstrap` half (cp uv + wheel, `uv tool install`, preflight) and only on success runs a `_spawn` half (detached `nohup` launch). Failures surface in the existing unified log; the runtime stays `disconnected` (no schema/state change).

**Tech Stack:** Python 3.13, typer, urllib (stdlib), pytest, asyncio.

## Global Constraints

- Python checks from repo root: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Container log path: `/tmp/vibing-runtime.log` (constant `CONTAINER_LOG_PATH`). PID path: `/tmp/vibing-runtime.pid` (`CONTAINER_PID_PATH`).
- Runtime WS endpoint path suffix: `/runtime/agent/ws`. Health endpoint: `/api/v1/health`.
- `inject()` keeps its `bool` contract (True = runtime launched). Do **not** touch `RuntimeService`, the `launching` transient, the API schema, the runtime-state model, or the frontend.
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- No new dependencies — `urllib` only.

---

### Task 1: `vibing runtime preflight` command

**Files:**
- Create: `src/vibing_devcontainer_runtime/preflight.py`
- Modify: `src/vibing_cli/__init__.py` (wire sibling command under `runtime_app`)
- Test: `tests/devcontainer_runtime/test_preflight.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `health_url_from_ws(ws_url: str) -> str` — `ws`→`http`/`wss`→`https`, path suffix `/runtime/agent/ws`→`/health`, host+port preserved.
  - `check_reachable(ws_url: str, timeout: float = 5.0) -> tuple[bool, str]` — `(ok, message)`; message starts with `PREFLIGHT FAILED:` on failure.
  - `preflight(control_plane_url: str)` — typer command; exit 0 on reachable, exit 1 otherwise.
  - CLI: `vibing runtime preflight --control-plane-url <ws-url>`.

- [ ] **Step 1: Write the failing tests**

Create `tests/devcontainer_runtime/test_preflight.py`:

```python
"""Tests for the in-container preflight reachability probe."""

import urllib.error

import pytest
from typer.testing import CliRunner

from vibing_cli import app
from vibing_devcontainer_runtime import preflight as pf


def test_health_url_swaps_scheme_and_path() -> None:
    assert (
        pf.health_url_from_ws("ws://10.0.0.5:8080/api/v1/runtime/agent/ws")
        == "http://10.0.0.5:8080/api/v1/health"
    )


def test_health_url_handles_wss_and_preserves_port() -> None:
    assert (
        pf.health_url_from_ws("wss://cp.example:9443/api/v1/runtime/agent/ws")
        == "https://cp.example:9443/api/v1/health"
    )


class _Resp:
    status = 200

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_check_reachable_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf, "urlopen", lambda url, timeout: _Resp())
    ok, message = pf.check_reachable("ws://cp:8080/api/v1/runtime/agent/ws")
    assert ok is True
    assert "http://cp:8080/api/v1/health" in message


def test_check_reachable_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, timeout: float) -> object:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(pf, "urlopen", boom)
    ok, message = pf.check_reachable("ws://cp:8080/api/v1/runtime/agent/ws")
    assert ok is False
    assert message.startswith("PREFLIGHT FAILED:")
    assert "http://cp:8080/api/v1/health" in message


def test_cli_preflight_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf, "check_reachable", lambda url: (True, "ok"))
    ok_result = CliRunner().invoke(
        app, ["runtime", "preflight", "--control-plane-url", "ws://cp:8080/api/v1/runtime/agent/ws"]
    )
    assert ok_result.exit_code == 0, ok_result.output

    monkeypatch.setattr(pf, "check_reachable", lambda url: (False, "PREFLIGHT FAILED: nope"))
    bad_result = CliRunner().invoke(
        app, ["runtime", "preflight", "--control-plane-url", "ws://cp:8080/api/v1/runtime/agent/ws"]
    )
    assert bad_result.exit_code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/devcontainer_runtime/test_preflight.py -q`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError` (no `preflight` module, command not wired).

- [ ] **Step 3: Create the preflight module**

Create `src/vibing_devcontainer_runtime/preflight.py`:

```python
"""In-container preflight: probe the Control Plane health endpoint before spawning.

Runs after bootstrap (vibing is installed). GETs the HTTP health endpoint derived from
the same resolved WS URL the runtime will connect to, so a wrong resolved URL fails here
instead of after a silent spawn. Failure leaves a clear line in the unified log.
"""

import urllib.error
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

import typer

_WS_TO_HTTP = {"ws": "http", "wss": "https"}
_RUNTIME_PATH_SUFFIX = "/runtime/agent/ws"
_HEALTH_PATH = "/health"


def health_url_from_ws(ws_url: str) -> str:
    parsed = urlparse(ws_url)
    scheme = _WS_TO_HTTP.get(parsed.scheme, parsed.scheme)
    path = parsed.path
    if path.endswith(_RUNTIME_PATH_SUFFIX):
        path = path[: -len(_RUNTIME_PATH_SUFFIX)] + _HEALTH_PATH
    else:
        path = _HEALTH_PATH
    return urlunparse(parsed._replace(scheme=scheme, path=path))


def check_reachable(ws_url: str, timeout: float = 5.0) -> tuple[bool, str]:
    health = health_url_from_ws(ws_url)
    try:
        with urlopen(health, timeout=timeout) as resp:
            if resp.status == 200:
                return True, f"preflight ok: control plane reachable at {health}"
            return False, f"PREFLIGHT FAILED: control plane unreachable at {health}: HTTP {resp.status}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"PREFLIGHT FAILED: control plane unreachable at {health}: {exc}"


def preflight(
    control_plane_url: str = typer.Option(..., help="Control Plane WS URL"),
) -> None:
    """Exit 0 if the Control Plane health endpoint is reachable, else exit 1."""
    ok, message = check_reachable(control_plane_url)
    if ok:
        typer.echo(message)
        raise typer.Exit(0)
    typer.echo(message, err=True)
    raise typer.Exit(1)
```

- [ ] **Step 4: Wire the command as a sibling of `runtime devcontainer`**

In `src/vibing_cli/__init__.py`, add the import near the existing runtime import:

```python
from vibing_devcontainer_runtime.cli import cli as devcontainer_runtime_app
from vibing_devcontainer_runtime.preflight import preflight as runtime_preflight
```

Then, right after the existing `runtime_app.add_typer(devcontainer_runtime_app, name="devcontainer")` line, register the command:

```python
runtime_app.command("preflight")(runtime_preflight)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/devcontainer_runtime/test_preflight.py -q`
Expected: PASS (5 passed).

- [ ] **Step 6: Lint, format, type-check**

Run: `uv run ruff check src tests && uv run ruff format src tests && uv run mypy src`
Expected: clean. (`ruff format` may reformat the long f-string line — that is fine.)

- [ ] **Step 7: Commit**

```bash
git add src/vibing_devcontainer_runtime/preflight.py src/vibing_cli/__init__.py tests/devcontainer_runtime/test_preflight.py
git commit -m "feat(runtime): add vibing runtime preflight reachability probe

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Two-phase `inject()` — bootstrap+preflight gates spawn

**Files:**
- Modify: `src/vibing_api/core/runtime_injector.py` (`inject`, new `_bootstrap`/`_spawn`)
- Test: `tests/api/test_runtime_injector.py`

**Interfaces:**
- Consumes: `vibing runtime preflight --control-plane-url <url>` (Task 1) — referenced in the bootstrap payload string.
- Produces: `inject()` unchanged signature `(devcontainer_id, container_id, local_path) -> bool`. Internally issues **two** `devcontainer exec` calls: bootstrap (install + preflight) then, only on success, spawn (`nohup` launch + PID). The same resolved `agent_url` appears in both the preflight and the launch.

- [ ] **Step 1: Update the existing payload test and add the two new tests**

In `tests/api/test_runtime_injector.py`, **replace** `test_inject_payload_installs_synchronously_and_detaches_only_runtime` with the two-phase version below, and **add** the two new tests after it:

```python
def test_inject_runs_bootstrap_then_spawn_with_same_url(tmp_path: Path) -> None:
    payloads = []

    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[:2] == ["devcontainer", "exec"]:
            payloads.append(command[-1])
        return RunResult(0, "", "")

    injector = RuntimeInjector(
        runner=runner,
        wheel_dir=_wheel_dir(tmp_path),
        runtime_control_plane_url="ws://cp:8080/api/v1/runtime/agent/ws",
    )
    assert asyncio.run(injector.inject_by_path("dc1", "/work/repo")) is True

    assert len(payloads) == 2
    bootstrap, spawn = payloads

    # half 1: install synchronously + preflight, NOT the runtime
    assert "set -e" in bootstrap and "pipefail" in bootstrap
    assert f"tee {CONTAINER_LOG_PATH}" in bootstrap
    assert "vibing runtime preflight --control-plane-url ws://cp:8080/api/v1/runtime/agent/ws" in bootstrap
    assert "nohup" not in bootstrap

    # half 2: detached runtime + PID, same resolved url
    assert "nohup vibing runtime devcontainer" in spawn
    assert "--control-plane-url ws://cp:8080/api/v1/runtime/agent/ws" in spawn
    assert f"echo $! >{CONTAINER_PID_PATH}" in spawn


def test_inject_skips_spawn_when_bootstrap_fails(tmp_path: Path) -> None:
    payloads = []

    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        if command[:2] == ["devcontainer", "exec"]:
            payloads.append(command[-1])
            if "preflight" in command[-1]:
                return RunResult(1, "", "PREFLIGHT FAILED: control plane unreachable")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir=_wheel_dir(tmp_path))
    assert asyncio.run(injector.inject_by_path("dc1", "/work/repo")) is False

    # only the bootstrap exec ran; spawn was skipped
    assert len(payloads) == 1
    assert "nohup" not in payloads[0]
```

- [ ] **Step 2: Run the injector tests to verify the new ones fail**

Run: `uv run pytest tests/api/test_runtime_injector.py -q`
Expected: the two new tests FAIL — currently `inject` issues a single exec containing both install and `nohup`, so `len(payloads) == 2` and the `"nohup" not in bootstrap` assertions fail.

- [ ] **Step 3: Split `inject()` into `_bootstrap` and `_spawn`**

In `src/vibing_api/core/runtime_injector.py`, replace the body of `inject` (the method spanning the `wheel`/`cp`/`bash_payload`/`exec` block) with this orchestration plus the two halves. Keep everything else in the file unchanged:

```python
    async def inject(self, devcontainer_id: str, container_id: str, local_path: str) -> bool:
        logger.info("runtime injection: %s into container %s", devcontainer_id, container_id)
        agent_url = resolve_runtime_control_plane_url(self._runtime_url)
        if not await self._bootstrap(devcontainer_id, container_id, local_path, agent_url):
            return False
        return await self._spawn(devcontainer_id, local_path, agent_url)

    async def _bootstrap(
        self, devcontainer_id: str, container_id: str, local_path: str, agent_url: str
    ) -> bool:
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

        payload = (
            "set -e -o pipefail\n"
            f"{_CONTAINER_UV_DEST} tool install --python 3.13 --from {container_wheel_path} vibing"
            f" 2>&1 | tee {CONTAINER_LOG_PATH}\n"
            'export PATH="$HOME/.local/bin:$PATH"\n'
            f"vibing runtime preflight --control-plane-url {agent_url}"
            f" 2>&1 | tee -a {CONTAINER_LOG_PATH}\n"
        )
        return await self._exec(local_path, payload, "bootstrap", devcontainer_id)

    async def _spawn(self, devcontainer_id: str, local_path: str, agent_url: str) -> bool:
        payload = (
            'export PATH="$HOME/.local/bin:$PATH"\n'
            f"nohup vibing runtime devcontainer"
            f" --control-plane-url {agent_url}"
            f" --devcontainer-id {devcontainer_id}"
            f" >>{CONTAINER_LOG_PATH} 2>&1 &\n"
            f"echo $! >{CONTAINER_PID_PATH}\n"
        )
        if await self._exec(local_path, payload, "spawn", devcontainer_id):
            logger.info("runtime injection launched: %s (waiting for WS connect)", devcontainer_id)
            return True
        return False

    async def _exec(self, local_path: str, payload: str, step: str, context: str) -> bool:
        return await self._run(
            [self._cli, "exec", "--workspace-folder", local_path, "--", "bash", "-lc", payload],
            f"devcontainer exec ({step})",
            context,
        )
```

- [ ] **Step 4: Run the injector tests to verify all pass**

Run: `uv run pytest tests/api/test_runtime_injector.py -q`
Expected: PASS (all tests, including `test_inject_by_path_resolves_container_then_injects`, `test_inject_returns_false_when_a_step_fails`, `test_stop_runtime_kills_via_pid_file`, both stream tests, and the two new ones).

- [ ] **Step 5: Run the full backend suite + checks**

Run: `uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`
Expected: all green. (If `ruff format --check` complains about the new file, run `uv run ruff format src tests` and re-stage.)

- [ ] **Step 6: Commit**

```bash
git add src/vibing_api/core/runtime_injector.py tests/api/test_runtime_injector.py
git commit -m "feat(api): two-phase inject — preflight gates runtime spawn

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Documentation coherence

**Files:**
- Modify: `docs/adr/0017-the-devcontainer-runtime-has-a-user-driven-control-plane-observed-lifecycle.md` (amendment note)
- Modify: `CONTEXT.md` (Runtime lifecycle section)
- Modify: `src/vibing_api/CLAUDE.md` (`runtime_injector.py` line)
- Modify: `src/vibing_devcontainer_runtime/CLAUDE.md` (new preflight file + context)
- Modify: `src/vibing_cli/CLAUDE.md` (new `runtime preflight` command)

**Interfaces:**
- Consumes: the behavior built in Tasks 1–2. No code; documentation only.
- Produces: docs consistent with two-phase inject + preflight.

- [ ] **Step 1: Amend ADR-0017**

At the end of `docs/adr/0017-...md`, immediately before the `Status: accepted` line, add this paragraph:

```markdown
**Amendment (2026-06-23): inject is two-phase, preflight gates spawn.** `inject()` now runs
in two halves: **bootstrap+preflight** (`docker cp` uv + wheel, `uv tool install`, then a
`vibing runtime preflight` HTTP `GET` of the control-plane `/api/v1/health` derived from the
*same resolved WS URL* the runtime will use) and **spawn** (the detached `nohup` launch),
issued as two separate `devcontainer exec` calls. The runtime is spawned **only if
bootstrap+preflight succeeds**, so an unreachable control plane (a wrong resolved IP — the
most common silent failure) fails before any process is launched. Surfacing stays log-only
and the resolved state stays coarse `disconnected`: the `PREFLIGHT FAILED:` line lands in the
unified log, streamed by [0018].
```

- [ ] **Step 2: Update CONTEXT.md**

In `CONTEXT.md`, in the `### Runtime lifecycle` section, replace the sentence beginning "Diagnosability splits two ways" through "...silently retried." with:

```markdown
Diagnosability splits two ways: **bootstrap + preflight** (`docker cp`, `uv tool install`, then
a `vibing runtime preflight` HTTP probe of the control-plane `/api/v1/health`) runs first and is
reported **synchronously** at inject time; the runtime is **spawned only if that half passes**, so
an unreachable control plane fails before any process starts. **Post-launch output** lives in the
in-container runtime log, **streamed live** (`tail -f`) over a chunked-HTTP `runtime-logs/stream`
endpoint while the Logs view is open. There is no in-container supervisor and no auto-restart —
failures (including a failed preflight) surface to the user rather than being silently retried.
```

- [ ] **Step 3: Update `src/vibing_api/CLAUDE.md`**

Replace the `core/runtime_injector.py:` bullet with:

```markdown
- `core/runtime_injector.py`: two-phase `inject()` — `_bootstrap` (`docker cp` uv + wheel, synchronous `uv tool install` teed to `/tmp/vibing-runtime.log`, then a `vibing runtime preflight` HTTP probe of the control-plane `/api/v1/health`) then, **only on success**, `_spawn` (detached `nohup` launch with PID in `/tmp/vibing-runtime.pid`). Two separate `devcontainer exec` calls; the same resolved control-plane URL is used by both the preflight and the launch. `inject*` return `bool` (bootstrap+preflight ok). Also `stop_runtime` (`<engine> exec` kill via PID file) and `stream_log` (async generator, `tail -n +1 -f` via injectable `log_streamer`).
```

- [ ] **Step 4: Update `src/vibing_devcontainer_runtime/CLAUDE.md`**

Add a bullet under `## Files` after the `cli.py` bullet:

```markdown
- `preflight.py`: `vibing runtime preflight --control-plane-url <ws-url>` — HTTP `GET` of the control-plane health endpoint (derived from the WS URL: `ws`→`http`, `/runtime/agent/ws`→`/api/v1/health`). Exit 0 if reachable, else exit 1 with a `PREFLIGHT FAILED:` line. Run inside the container during inject's bootstrap half, before the runtime is spawned.
```

And in `## Context`, replace the bullet starting "Launched detached by the Control Plane's injector" with:

```markdown
- Launched detached by the Control Plane's injector **only after** its bootstrap half (`uv tool install` + a `vibing runtime preflight` reachability probe) succeeds; the install, the preflight result, and the runtime's stdout/stderr are all teed to `/tmp/vibing-runtime.log`, and its PID recorded in `/tmp/vibing-runtime.pid` for `stop-runtime`.
```

- [ ] **Step 5: Update `src/vibing_cli/CLAUDE.md`**

After the `vibing runtime devcontainer ...` bullet, add:

```markdown
- `vibing runtime preflight --control-plane-url ...`: in-container reachability probe of the control-plane health endpoint (`vibing_devcontainer_runtime.preflight`); exit 0/1.
```

- [ ] **Step 6: Verify docs reference reality**

Run: `uv run pytest -q`
Expected: PASS (docs-only change; confirms nothing else drifted). Re-read each edited file to confirm no dangling references to a one-shot inject.

- [ ] **Step 7: Commit**

```bash
git add docs/adr/0017-the-devcontainer-runtime-has-a-user-driven-control-plane-observed-lifecycle.md CONTEXT.md src/vibing_api/CLAUDE.md src/vibing_devcontainer_runtime/CLAUDE.md src/vibing_cli/CLAUDE.md
git commit -m "docs: two-phase inject + preflight coherence (ADR-0017, CONTEXT, CLAUDE.md)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Preflight command (HTTP health probe, derived URL, 5s, exit codes) → Task 1. ✓
- Two-phase `inject()` (`_bootstrap` gates `_spawn`, same `agent_url` both halves, unified log) → Task 2. ✓
- Log-only surfacing, no schema/state/frontend change → enforced by Global Constraints + Task 2 keeping the `bool` contract. ✓
- Tests (URL derivation, reachable/unreachable, spawn-skipped-on-failure, order) → Tasks 1 & 2. ✓
- Docs coherence (ADR-0017, CONTEXT, 3× CLAUDE.md) → Task 3. ✓
- Non-goals (no distinct state, no retry, no cached bootstrap) → respected; nothing in the plan adds them. ✓

**Placeholder scan:** none — all steps contain real code/commands.

**Type consistency:** `health_url_from_ws`/`check_reachable`/`preflight` signatures match between Task 1's module, its tests, and the wiring. `inject`/`_bootstrap`/`_spawn`/`_exec` names and `bool` returns are consistent across Task 2's code and tests. `RuntimeInjector(runtime_control_plane_url=...)` kwarg matches the existing `__init__` parameter name.
