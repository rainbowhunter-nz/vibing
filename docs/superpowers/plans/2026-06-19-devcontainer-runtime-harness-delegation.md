# Devcontainer Runtime — Managed Harnesses & MCP Delegation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-scope the Devcontainer Runtime Agent so it can check/install/authenticate managed coding harnesses (Codex, Cursor) and host an MCP server the main harness calls to spawn unattended Delegated Runs.

**Architecture:** Implements ADR-0011/0012/0013 (runtime side only). A per-harness **adapter** owns each harness's install command, credential location, auth check, and non-interactive invocation. A **HarnessManager** drives adapters for the `authenticate_harness` Command and status queries. A **DelegatedRunManager** runs harnesses to completion (concurrent, capped) and emits Delegated Run runtime events. A **FastMCP streamable-HTTP server** exposes `list_harnesses`/`spawn`/`get_status`/`get_result`/`stop`. `cli.py serve` runs the existing WebSocket channel client and the MCP server concurrently in one asyncio loop. The existing Agent Session path is untouched (coexists).

**Tech Stack:** Python 3.13, asyncio, Pydantic v2, Typer, logzero, `mcp` (Python SDK / FastMCP), uvicorn (already a dep), pytest.

**Out of scope (separate follow-up plan — "Control Plane credential pipeline"):** the `vibing` host-capture command that reads a harness's on-disk auth file, Control Plane credential storage, the API/UI that *emits* `authenticate_harness`, and any new Control Plane projection of harness-status / Delegated Run events. This plan makes the runtime *handle* those events; it does not build the Control Plane side. Delegated Run and harness-status events are carried in `RuntimeEvent.payload` (no new top-level column), so this plan does not touch the API schema, reducer, or migrations.

## Global Constraints

- Python `>=3.13`; all code typed for `mypy src` (strict project config).
- All checks must pass from repo root: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Dependency changes go through `uv` (`uv add ...`) — never hand-edit `pyproject.toml` dependency metadata. Load the `uv` skill.
- CLIs use Typer + rich; logging uses logzero.
- Protocol vocabularies are `StrEnum`s; values are wire strings via `auto()`. Compare/construct with members, not raw strings.
- When adding a command/event type: add the enum member, then update handlers + tests + the package `CLAUDE.md`.
- Simplicity first: minimum code that solves the problem; no speculative abstraction. Prefer self-explanatory code over comments.
- Keep `CONTEXT.md` and `docs/adr/*` coherent (glossary terms **Coding Harness**, **Delegated Run** and ADR-0011/0012/0013 already exist on this branch).
- Default MCP bind: `127.0.0.1:8848` (no MCP-level auth — single-user, isolated container).
- Managed harnesses run **fully autonomous** (bypass mode). Concurrency cap default **4**.

---

## File Structure

New package `src/vibing_devcontainer_runtime/harness/`:
- `process.py` — `CompletedCommand`, `HarnessProcess` seam, `real_process_factory`, `run_to_completion` helper.
- `base.py` — `HarnessAdapter` ABC, `HarnessStatus` dataclass.
- `codex.py` — `CodexAdapter`.
- `cursor.py` — `CursorAdapter`.
- `registry.py` — `build_adapters(...)` → `dict[str, HarnessAdapter]`.

New modules in `src/vibing_devcontainer_runtime/`:
- `harness_manager.py` — `HarnessManager` (status + authenticate).
- `delegated_runs.py` — `DelegatedRunManager` (spawn/status/result/stop, cap, events).
- `mcp_server.py` — `build_mcp_server(...)` → configured `FastMCP`.

Modified:
- `src/vibing_protocol/commands.py`, `src/vibing_protocol/runtime_events.py` — new enum members.
- `src/vibing_devcontainer_runtime/command_handler.py` — handle `AUTHENTICATE_HARNESS`.
- `src/vibing_devcontainer_runtime/cli.py` — run channel client + MCP server concurrently; new options.
- `src/vibing_devcontainer_runtime/CLAUDE.md`, `src/vibing_protocol/CLAUDE.md` — docs.

Tests mirror under `tests/devcontainer_runtime/` and `tests/protocol/`.

---

### Task 1: Protocol — new Command and Event types

**Files:**
- Modify: `src/vibing_protocol/commands.py:14-24`
- Modify: `src/vibing_protocol/runtime_events.py:16-31`
- Test: `tests/protocol/test_harness_vocab.py` (create)

**Interfaces:**
- Produces: `CommandType.AUTHENTICATE_HARNESS`; `EventType.HARNESS_STATUS`, `EventType.DELEGATED_RUN_STARTED`, `EventType.DELEGATED_RUN_COMPLETED`, `EventType.DELEGATED_RUN_FAILED`. Wire strings equal the lowercased member names.

- [ ] **Step 1: Write the failing test**

```python
# tests/protocol/test_harness_vocab.py
from vibing_protocol import Command, CommandType, EventType, RuntimeEvent, RuntimeEventSource


def test_authenticate_harness_command_type_wire_value():
    assert CommandType.AUTHENTICATE_HARNESS == "authenticate_harness"
    cmd = Command(
        type=CommandType.AUTHENTICATE_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex", "credentials": {"auth_json": {"OPENAI_API_KEY": "sk-x"}}},
    )
    assert cmd.payload is not None
    assert cmd.payload["harness"] == "codex"


def test_delegated_run_and_harness_status_event_types():
    assert EventType.HARNESS_STATUS == "harness_status"
    assert EventType.DELEGATED_RUN_STARTED == "delegated_run_started"
    assert EventType.DELEGATED_RUN_COMPLETED == "delegated_run_completed"
    assert EventType.DELEGATED_RUN_FAILED == "delegated_run_failed"
    evt = RuntimeEvent(
        event_type=EventType.DELEGATED_RUN_COMPLETED,
        source=RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT,
        devcontainer_id="dc-1",
        payload={"delegated_run_id": "run-1", "result": "done"},
    )
    assert evt.payload is not None and evt.payload["delegated_run_id"] == "run-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/protocol/test_harness_vocab.py -q`
Expected: FAIL — `AttributeError: AUTHENTICATE_HARNESS` (member not defined).

- [ ] **Step 3: Add the enum members**

In `src/vibing_protocol/commands.py`, inside `class CommandType`, after `RESOLVE_APPROVAL = auto()`:

```python
    AUTHENTICATE_HARNESS = auto()
```

In `src/vibing_protocol/runtime_events.py`, inside `class EventType`, after `SESSION_STOPPED = auto()`:

```python
    HARNESS_STATUS = auto()
    DELEGATED_RUN_STARTED = auto()
    DELEGATED_RUN_COMPLETED = auto()
    DELEGATED_RUN_FAILED = auto()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/protocol/test_harness_vocab.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_protocol/commands.py src/vibing_protocol/runtime_events.py tests/protocol/test_harness_vocab.py
git commit -m "feat(protocol): add authenticate_harness command + harness/delegated-run events"
```

---

### Task 2: Harness subprocess seam (`process.py`)

**Files:**
- Create: `src/vibing_devcontainer_runtime/harness/__init__.py` (empty)
- Create: `src/vibing_devcontainer_runtime/harness/process.py`
- Test: `tests/devcontainer_runtime/test_harness_process.py` (create)

**Interfaces:**
- Produces:
  - `CompletedCommand(returncode: int, stdout: str, stderr: str)` (frozen dataclass).
  - `class HarnessProcess` with `async wait() -> CompletedCommand` and `async terminate() -> None`.
  - `HarnessProcessFactory = Callable[[list[str], str | None, dict[str, str] | None], HarnessProcess]` (args: argv, cwd, extra_env).
  - `real_process_factory(argv, cwd, env) -> HarnessProcess`.
  - `async run_to_completion(factory, argv, *, cwd=None, env=None) -> CompletedCommand`.
- Consumed by: Tasks 4, 5 (adapters) and Task 6 (delegated runs).

- [ ] **Step 1: Write the failing test**

```python
# tests/devcontainer_runtime/test_harness_process.py
import asyncio
import sys

from vibing_devcontainer_runtime.harness.process import (
    CompletedCommand,
    real_process_factory,
    run_to_completion,
)


def test_real_factory_runs_and_captures_stdout_and_exit():
    result = asyncio.run(
        run_to_completion(real_process_factory, [sys.executable, "-c", "print('hi')"])
    )
    assert isinstance(result, CompletedCommand)
    assert result.returncode == 0
    assert result.stdout.strip() == "hi"


def test_real_factory_missing_binary_returns_127_not_raise():
    result = asyncio.run(run_to_completion(real_process_factory, ["definitely-not-a-binary-xyz"]))
    assert result.returncode == 127


def test_extra_env_is_passed_to_child():
    code = "import os; print(os.environ.get('VIBING_TEST_VAR', 'missing'))"
    result = asyncio.run(
        run_to_completion(
            real_process_factory, [sys.executable, "-c", code], env={"VIBING_TEST_VAR": "present"}
        )
    )
    assert result.stdout.strip() == "present"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_harness_process.py -q`
Expected: FAIL — `ModuleNotFoundError: vibing_devcontainer_runtime.harness.process`.

- [ ] **Step 3: Create the package + module**

Create empty `src/vibing_devcontainer_runtime/harness/__init__.py`.

Create `src/vibing_devcontainer_runtime/harness/process.py`:

```python
"""Subprocess seam for harness commands.

One factory builds a HarnessProcess from (argv, cwd, extra_env); production runs a real
subprocess, tests inject a fake. Adapters use run_to_completion for short commands
(install / auth-check); the DelegatedRunManager keeps the HarnessProcess to terminate it.
"""

import asyncio
import os
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

_SIGTERM_GRACE_SECONDS = 5.0


@dataclass(frozen=True)
class CompletedCommand:
    returncode: int
    stdout: str
    stderr: str


class HarnessProcess:
    """Handle to a running (or fake) harness subprocess."""

    async def wait(self) -> CompletedCommand:
        raise NotImplementedError

    async def terminate(self) -> None:
        raise NotImplementedError


HarnessProcessFactory = Callable[[list[str], str | None, dict[str, str] | None], HarnessProcess]


class _RealProcess(HarnessProcess):
    def __init__(self, argv: list[str], cwd: str | None, env: dict[str, str] | None) -> None:
        self._argv = argv
        self._cwd = cwd
        self._env = {**os.environ, **env} if env else None
        self._proc: asyncio.subprocess.Process | None = None

    async def wait(self) -> CompletedCommand:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                env=self._env,
            )
        except FileNotFoundError:
            return CompletedCommand(returncode=127, stdout="", stderr="binary not found")
        out_b, err_b = await self._proc.communicate()
        return CompletedCommand(
            returncode=self._proc.returncode or 0,
            stdout=out_b.decode(errors="replace"),
            stderr=err_b.decode(errors="replace"),
        )

    async def terminate(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=_SIGTERM_GRACE_SECONDS)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass


def real_process_factory(
    argv: list[str], cwd: str | None, env: dict[str, str] | None
) -> HarnessProcess:
    return _RealProcess(argv, cwd, env)


async def run_to_completion(
    factory: HarnessProcessFactory,
    argv: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> CompletedCommand:
    return await factory(argv, cwd, env).wait()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/devcontainer_runtime/test_harness_process.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/harness/__init__.py src/vibing_devcontainer_runtime/harness/process.py tests/devcontainer_runtime/test_harness_process.py
git commit -m "feat(runtime): harness subprocess seam (HarnessProcess factory)"
```

---

### Task 3: Harness adapter base (`base.py`)

**Files:**
- Create: `src/vibing_devcontainer_runtime/harness/base.py`
- Test: `tests/devcontainer_runtime/test_harness_base.py` (create)

**Interfaces:**
- Produces:
  - `HarnessStatus(name: str, installed: bool, authenticated: bool)` (frozen dataclass).
  - `class HarnessAdapter(ABC)` with `name: str` attr and abstract methods:
    - `async is_installed() -> bool`
    - `async install() -> None`
    - `async is_authenticated() -> bool`
    - `write_credentials(blob: dict[str, Any]) -> None`
    - `build_spawn_argv(model: str, prompt: str) -> list[str]`
    - `spawn_env() -> dict[str, str]`
    - `extract_result(stdout: str) -> str`
- Consumed by: Tasks 4, 5, 6, 7.

- [ ] **Step 1: Write the failing test**

```python
# tests/devcontainer_runtime/test_harness_base.py
import pytest

from vibing_devcontainer_runtime.harness.base import HarnessAdapter, HarnessStatus


def test_harness_status_fields():
    s = HarnessStatus(name="codex", installed=True, authenticated=False)
    assert (s.name, s.installed, s.authenticated) == ("codex", True, False)


def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        HarnessAdapter()  # type: ignore[abstract]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_harness_base.py -q`
Expected: FAIL — `ModuleNotFoundError: ...harness.base`.

- [ ] **Step 3: Create `base.py`**

```python
"""HarnessAdapter: the per-harness contract. The single place that knows a harness's
install command, credential location/format, auth check, and non-interactive invocation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HarnessStatus:
    name: str
    installed: bool
    authenticated: bool


class HarnessAdapter(ABC):
    name: str

    @abstractmethod
    async def is_installed(self) -> bool: ...

    @abstractmethod
    async def install(self) -> None: ...

    @abstractmethod
    async def is_authenticated(self) -> bool: ...

    @abstractmethod
    def write_credentials(self, blob: dict[str, Any]) -> None: ...

    @abstractmethod
    def build_spawn_argv(self, model: str, prompt: str) -> list[str]: ...

    @abstractmethod
    def spawn_env(self) -> dict[str, str]: ...

    @abstractmethod
    def extract_result(self, stdout: str) -> str: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/devcontainer_runtime/test_harness_base.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/harness/base.py tests/devcontainer_runtime/test_harness_base.py
git commit -m "feat(runtime): HarnessAdapter base contract + HarnessStatus"
```

---

### Task 4: Codex adapter (`codex.py`)

**Files:**
- Create: `src/vibing_devcontainer_runtime/harness/codex.py`
- Test: `tests/devcontainer_runtime/test_codex_adapter.py` (create)

**Verified CLI facts (research; verify against `codex --help` on the target version):** install `npm install -g @openai/codex`; non-interactive `codex exec "<prompt>"`; model `--model <m>`; fully-unattended `--dangerously-bypass-approvals-and-sandbox`; auth file `~/.codex/auth.json` (plaintext JSON; API-key key `OPENAI_API_KEY`, or ChatGPT `auth_mode`/`tokens`); auth check `codex login status` (exit 0 = authed); default `exec` prints the final assistant message as text to stdout.

**Interfaces:**
- Consumes: `HarnessAdapter`, `HarnessProcessFactory`, `run_to_completion` (Tasks 2-3).
- Produces: `CodexAdapter(factory: HarnessProcessFactory, home: Path)`. `name = "codex"`. Blob shape: `{"auth_json": <dict>}` → written to `<home>/.codex/auth.json` (mode 0600).

- [ ] **Step 1: Write the failing test**

```python
# tests/devcontainer_runtime/test_codex_adapter.py
import asyncio
import json
from pathlib import Path

from vibing_devcontainer_runtime.harness.codex import CodexAdapter
from vibing_devcontainer_runtime.harness.process import CompletedCommand, HarnessProcess


class FakeProcess(HarnessProcess):
    def __init__(self, result: CompletedCommand) -> None:
        self._result = result

    async def wait(self) -> CompletedCommand:
        return self._result

    async def terminate(self) -> None:
        pass


def make_factory(by_argv):
    calls = []

    def factory(argv, cwd, env):
        calls.append((argv, cwd, env))
        return FakeProcess(by_argv(argv))

    factory.calls = calls  # type: ignore[attr-defined]
    return factory


def test_name():
    assert CodexAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), Path("/tmp")).name == "codex"


def test_is_installed_true_on_version_exit_zero(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "codex 1.2.3", ""))
    adapter = CodexAdapter(factory, tmp_path)
    assert asyncio.run(adapter.is_installed()) is True
    assert factory.calls[0][0] == ["codex", "--version"]


def test_is_installed_false_when_missing(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(127, "", "not found"))
    assert asyncio.run(CodexAdapter(factory, tmp_path).is_installed()) is False


def test_is_authenticated_uses_login_status_exit_code(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "Logged in", ""))
    adapter = CodexAdapter(factory, tmp_path)
    assert asyncio.run(adapter.is_authenticated()) is True
    assert factory.calls[0][0] == ["codex", "login", "status"]


def test_write_credentials_writes_auth_json_0600(tmp_path):
    adapter = CodexAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    adapter.write_credentials({"auth_json": {"OPENAI_API_KEY": "sk-test"}})
    path = tmp_path / ".codex" / "auth.json"
    assert json.loads(path.read_text()) == {"OPENAI_API_KEY": "sk-test"}
    assert (path.stat().st_mode & 0o777) == 0o600


def test_build_spawn_argv_is_fully_autonomous(tmp_path):
    adapter = CodexAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    argv = adapter.build_spawn_argv("gpt-5.4", "fix the bug")
    assert argv == [
        "codex", "exec",
        "--model", "gpt-5.4",
        "--dangerously-bypass-approvals-and-sandbox",
        "fix the bug",
    ]


def test_install_runs_npm_global(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "", ""))
    asyncio.run(CodexAdapter(factory, tmp_path).install())
    assert factory.calls[0][0] == ["npm", "install", "-g", "@openai/codex"]


def test_extract_result_returns_trimmed_stdout(tmp_path):
    adapter = CodexAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    assert adapter.extract_result("  final answer\n") == "final answer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_codex_adapter.py -q`
Expected: FAIL — `ModuleNotFoundError: ...harness.codex`.

- [ ] **Step 3: Create `codex.py`**

```python
"""CodexAdapter: OpenAI Codex CLI (`codex`). See ADR-0011/0012/0013."""

import json
from pathlib import Path
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.process import HarnessProcessFactory, run_to_completion

_BINARY = "codex"


class CodexAdapter(HarnessAdapter):
    name = "codex"

    def __init__(self, factory: HarnessProcessFactory, home: Path) -> None:
        self._factory = factory
        self._home = home

    @property
    def _auth_path(self) -> Path:
        return self._home / ".codex" / "auth.json"

    async def is_installed(self) -> bool:
        result = await run_to_completion(self._factory, [_BINARY, "--version"])
        return result.returncode == 0

    async def install(self) -> None:
        await run_to_completion(self._factory, ["npm", "install", "-g", "@openai/codex"])

    async def is_authenticated(self) -> bool:
        result = await run_to_completion(self._factory, [_BINARY, "login", "status"])
        return result.returncode == 0

    def write_credentials(self, blob: dict[str, Any]) -> None:
        self._auth_path.parent.mkdir(parents=True, exist_ok=True)
        self._auth_path.write_text(json.dumps(blob["auth_json"]))
        self._auth_path.chmod(0o600)

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [
            _BINARY, "exec",
            "--model", model,
            "--dangerously-bypass-approvals-and-sandbox",
            prompt,
        ]

    def spawn_env(self) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/devcontainer_runtime/test_codex_adapter.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/harness/codex.py tests/devcontainer_runtime/test_codex_adapter.py
git commit -m "feat(runtime): CodexAdapter (install/auth/spawn)"
```

---

### Task 5: Cursor adapter (`cursor.py`)

**Files:**
- Create: `src/vibing_devcontainer_runtime/harness/cursor.py`
- Test: `tests/devcontainer_runtime/test_cursor_adapter.py` (create)

**Verified CLI facts (research; verify against `cursor-agent --help`):** install `curl https://cursor.com/install -fsS | bash` (binary `cursor-agent` in `~/.local/bin`); non-interactive `cursor-agent -p "<prompt>"`; model `--model <m>`; unattended edits need `--force`; `--output-format text` prints only final message. **Credential storage on disk is uncertain (likely OS keyring)**, but API-key auth via env `CURSOR_API_KEY` is the documented automation path — so this adapter treats the blob as an API key: persist it to `<home>/.config/vibing-harness/cursor.json` and inject it as `CURSOR_API_KEY` at spawn. Auth = that key file exists and is non-empty.

**Interfaces:**
- Consumes: `HarnessAdapter`, `HarnessProcessFactory`, `run_to_completion`.
- Produces: `CursorAdapter(factory, home)`. `name = "cursor"`. Blob shape: `{"api_key": "<key>"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/devcontainer_runtime/test_cursor_adapter.py
import asyncio
import json
from pathlib import Path

from vibing_devcontainer_runtime.harness.cursor import CursorAdapter
from vibing_devcontainer_runtime.harness.process import CompletedCommand, HarnessProcess


class FakeProcess(HarnessProcess):
    def __init__(self, result: CompletedCommand) -> None:
        self._result = result

    async def wait(self) -> CompletedCommand:
        return self._result

    async def terminate(self) -> None:
        pass


def make_factory(by_argv):
    calls = []

    def factory(argv, cwd, env):
        calls.append((argv, cwd, env))
        return FakeProcess(by_argv(argv))

    factory.calls = calls  # type: ignore[attr-defined]
    return factory


def test_name(tmp_path):
    assert CursorAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path).name == "cursor"


def test_is_installed_checks_version(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "1.0", ""))
    adapter = CursorAdapter(factory, tmp_path)
    assert asyncio.run(adapter.is_installed()) is True
    assert factory.calls[0][0] == ["cursor-agent", "--version"]


def test_write_credentials_then_authenticated_and_env(tmp_path):
    adapter = CursorAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    assert asyncio.run(adapter.is_authenticated()) is False
    adapter.write_credentials({"api_key": "key-123"})
    path = tmp_path / ".config" / "vibing-harness" / "cursor.json"
    assert json.loads(path.read_text()) == {"api_key": "key-123"}
    assert asyncio.run(adapter.is_authenticated()) is True
    assert adapter.spawn_env() == {"CURSOR_API_KEY": "key-123"}


def test_build_spawn_argv_print_force_text(tmp_path):
    adapter = CursorAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    argv = adapter.build_spawn_argv("sonnet-4", "do it")
    assert argv == [
        "cursor-agent", "-p", "do it",
        "--model", "sonnet-4",
        "--force",
        "--output-format", "text",
    ]


def test_install_runs_curl_pipe_bash(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "", ""))
    asyncio.run(CursorAdapter(factory, tmp_path).install())
    argv = factory.calls[0][0]
    assert argv[0] == "bash" and "cursor.com/install" in " ".join(argv)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_cursor_adapter.py -q`
Expected: FAIL — `ModuleNotFoundError: ...harness.cursor`.

- [ ] **Step 3: Create `cursor.py`**

```python
"""CursorAdapter: Cursor CLI (`cursor-agent`). See ADR-0011/0012/0013.

On-disk credential storage is uncertain (likely OS keyring); the documented automation
path is the CURSOR_API_KEY env var, so the blob is an API key persisted to our own config
file and injected as env at spawn.
"""

import json
from pathlib import Path
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.process import HarnessProcessFactory, run_to_completion

_BINARY = "cursor-agent"
_INSTALL = "curl https://cursor.com/install -fsS | bash"


class CursorAdapter(HarnessAdapter):
    name = "cursor"

    def __init__(self, factory: HarnessProcessFactory, home: Path) -> None:
        self._factory = factory
        self._home = home

    @property
    def _key_path(self) -> Path:
        return self._home / ".config" / "vibing-harness" / "cursor.json"

    def _api_key(self) -> str:
        if not self._key_path.exists():
            return ""
        return json.loads(self._key_path.read_text()).get("api_key", "")

    async def is_installed(self) -> bool:
        result = await run_to_completion(self._factory, [_BINARY, "--version"])
        return result.returncode == 0

    async def install(self) -> None:
        await run_to_completion(self._factory, ["bash", "-c", _INSTALL])

    async def is_authenticated(self) -> bool:
        return bool(self._api_key())

    def write_credentials(self, blob: dict[str, Any]) -> None:
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.write_text(json.dumps({"api_key": blob["api_key"]}))
        self._key_path.chmod(0o600)

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [_BINARY, "-p", prompt, "--model", model, "--force", "--output-format", "text"]

    def spawn_env(self) -> dict[str, str]:
        key = self._api_key()
        return {"CURSOR_API_KEY": key} if key else {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/devcontainer_runtime/test_cursor_adapter.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/harness/cursor.py tests/devcontainer_runtime/test_cursor_adapter.py
git commit -m "feat(runtime): CursorAdapter (api-key auth/spawn)"
```

---

### Task 6: Adapter registry (`registry.py`)

**Files:**
- Create: `src/vibing_devcontainer_runtime/harness/registry.py`
- Test: `tests/devcontainer_runtime/test_harness_registry.py` (create)

**Interfaces:**
- Consumes: `CodexAdapter`, `CursorAdapter`, `HarnessProcessFactory`, `real_process_factory`.
- Produces: `build_adapters(factory: HarnessProcessFactory | None = None, home: Path | None = None) -> dict[str, HarnessAdapter]` keyed by `name`. Defaults: `real_process_factory`, `Path.home()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/devcontainer_runtime/test_harness_registry.py
from pathlib import Path

from vibing_devcontainer_runtime.harness.codex import CodexAdapter
from vibing_devcontainer_runtime.harness.cursor import CursorAdapter
from vibing_devcontainer_runtime.harness.registry import build_adapters


def test_registry_has_codex_and_cursor(tmp_path):
    def factory(argv, cwd, env):  # not invoked here
        raise AssertionError

    adapters = build_adapters(factory, tmp_path)
    assert set(adapters) == {"codex", "cursor"}
    assert isinstance(adapters["codex"], CodexAdapter)
    assert isinstance(adapters["cursor"], CursorAdapter)


def test_registry_defaults_to_real_factory_and_home():
    adapters = build_adapters()
    assert set(adapters) == {"codex", "cursor"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_harness_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: ...harness.registry`.

- [ ] **Step 3: Create `registry.py`**

```python
"""build_adapters: name -> HarnessAdapter. The list of managed harnesses lives here."""

from pathlib import Path

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.codex import CodexAdapter
from vibing_devcontainer_runtime.harness.cursor import CursorAdapter
from vibing_devcontainer_runtime.harness.process import HarnessProcessFactory, real_process_factory


def build_adapters(
    factory: HarnessProcessFactory | None = None, home: Path | None = None
) -> dict[str, HarnessAdapter]:
    factory = factory or real_process_factory
    home = home or Path.home()
    adapters: list[HarnessAdapter] = [CodexAdapter(factory, home), CursorAdapter(factory, home)]
    return {a.name: a for a in adapters}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/devcontainer_runtime/test_harness_registry.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/harness/registry.py tests/devcontainer_runtime/test_harness_registry.py
git commit -m "feat(runtime): harness adapter registry"
```

---

### Task 7: HarnessManager (status + authenticate)

**Files:**
- Create: `src/vibing_devcontainer_runtime/harness_manager.py`
- Test: `tests/devcontainer_runtime/test_harness_manager.py` (create)

**Interfaces:**
- Consumes: `dict[str, HarnessAdapter]`, `HarnessStatus`.
- Produces: `HarnessManager(adapters: dict[str, HarnessAdapter])` with:
  - `async list_statuses() -> list[HarnessStatus]` — each adapter's installed/authenticated.
  - `async authenticate(harness: str, blob: dict[str, Any]) -> HarnessStatus` — install if missing, write creds, return fresh status. Unknown harness → `KeyError`.
- Consumed by: Tasks 8 (command handler), 9 (delegated runs uses adapters dict directly), 10 (MCP `list_harnesses`).

- [ ] **Step 1: Write the failing test**

```python
# tests/devcontainer_runtime/test_harness_manager.py
import asyncio
from typing import Any

import pytest

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness_manager import HarnessManager


class FakeAdapter(HarnessAdapter):
    def __init__(self, name: str, installed: bool, authed: bool) -> None:
        self.name = name
        self._installed = installed
        self._authed = authed
        self.installed_called = False
        self.written: dict[str, Any] | None = None

    async def is_installed(self) -> bool:
        return self._installed

    async def install(self) -> None:
        self.installed_called = True
        self._installed = True

    async def is_authenticated(self) -> bool:
        return self._authed

    def write_credentials(self, blob: dict[str, Any]) -> None:
        self.written = blob
        self._authed = True

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return []

    def spawn_env(self) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout


def test_list_statuses_reports_each_adapter():
    mgr = HarnessManager({"codex": FakeAdapter("codex", True, False),
                          "cursor": FakeAdapter("cursor", False, False)})
    statuses = {s.name: s for s in asyncio.run(mgr.list_statuses())}
    assert statuses["codex"].installed is True and statuses["codex"].authenticated is False
    assert statuses["cursor"].installed is False


def test_authenticate_installs_when_missing_then_writes_creds():
    adapter = FakeAdapter("codex", installed=False, authed=False)
    mgr = HarnessManager({"codex": adapter})
    status = asyncio.run(mgr.authenticate("codex", {"auth_json": {"k": "v"}}))
    assert adapter.installed_called is True
    assert adapter.written == {"auth_json": {"k": "v"}}
    assert status.installed is True and status.authenticated is True


def test_authenticate_unknown_harness_raises():
    mgr = HarnessManager({"codex": FakeAdapter("codex", True, True)})
    with pytest.raises(KeyError):
        asyncio.run(mgr.authenticate("nope", {}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_harness_manager.py -q`
Expected: FAIL — `ModuleNotFoundError: ...harness_manager`.

- [ ] **Step 3: Create `harness_manager.py`**

```python
"""HarnessManager: drives adapters for status queries and the authenticate_harness command."""

import asyncio
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessAdapter, HarnessStatus


class HarnessManager:
    def __init__(self, adapters: dict[str, HarnessAdapter]) -> None:
        self._adapters = adapters

    async def _status(self, adapter: HarnessAdapter) -> HarnessStatus:
        installed = await adapter.is_installed()
        authenticated = await adapter.is_authenticated() if installed else False
        return HarnessStatus(name=adapter.name, installed=installed, authenticated=authenticated)

    async def list_statuses(self) -> list[HarnessStatus]:
        return list(await asyncio.gather(*(self._status(a) for a in self._adapters.values())))

    async def authenticate(self, harness: str, blob: dict[str, Any]) -> HarnessStatus:
        adapter = self._adapters[harness]  # KeyError on unknown harness
        if not await adapter.is_installed():
            await adapter.install()
        adapter.write_credentials(blob)
        return await self._status(adapter)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/devcontainer_runtime/test_harness_manager.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/harness_manager.py tests/devcontainer_runtime/test_harness_manager.py
git commit -m "feat(runtime): HarnessManager (status + authenticate)"
```

---

### Task 8: Handle `authenticate_harness` in AgentCommandHandler

**Files:**
- Modify: `src/vibing_devcontainer_runtime/command_handler.py:47-69`
- Test: `tests/devcontainer_runtime/test_command_handler_harness.py` (create)

**Interfaces:**
- Consumes: `HarnessManager` (Task 7), `EventType.HARNESS_STATUS`, existing `AgentCommandHandler`, `SendFn`/`_make_emit`.
- Produces: `AgentCommandHandler(runner, harness_manager: HarnessManager | None = None)`. On `AUTHENTICATE_HARNESS` it calls `harness_manager.authenticate(harness, credentials)` and emits one `HARNESS_STATUS` event with payload `{"harness", "installed", "authenticated"}`. If no manager is wired, it logs and emits nothing (keeps existing tests green).

- [ ] **Step 1: Write the failing test**

```python
# tests/devcontainer_runtime/test_command_handler_harness.py
import asyncio
from typing import Any

from pydantic import BaseModel

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner
from vibing_devcontainer_runtime.command_handler import AgentCommandHandler
from vibing_devcontainer_runtime.harness.base import HarnessStatus
from vibing_protocol import Command, CommandType, RuntimeEventEnvelope


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def authenticate(self, harness: str, blob: dict[str, Any]) -> HarnessStatus:
        self.calls.append((harness, blob))
        return HarnessStatus(name=harness, installed=True, authenticated=True)


async def _collect(handler: AgentCommandHandler, command: Command) -> list[BaseModel]:
    sent: list[BaseModel] = []

    async def send(env: BaseModel) -> None:
        sent.append(env)

    await handler.handle(command, send)
    return sent


def test_authenticate_harness_emits_harness_status():
    manager = FakeManager()
    handler = AgentCommandHandler(ClaudeCodeRunner(), harness_manager=manager)  # type: ignore[arg-type]
    cmd = Command(
        type=CommandType.AUTHENTICATE_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex", "credentials": {"auth_json": {"OPENAI_API_KEY": "sk"}}},
    )
    sent = asyncio.run(_collect(handler, cmd))
    assert manager.calls == [("codex", {"auth_json": {"OPENAI_API_KEY": "sk"}})]
    envelopes = [e for e in sent if isinstance(e, RuntimeEventEnvelope)]
    assert len(envelopes) == 1
    evt = envelopes[0].event
    assert evt.event_type == "harness_status"
    assert evt.payload == {"harness": "codex", "installed": True, "authenticated": True}
    assert evt.devcontainer_id == "dc-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_command_handler_harness.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'harness_manager'`.

- [ ] **Step 3: Wire the handler**

In `command_handler.py`, update the import block to add `HarnessManager`:

```python
from vibing_devcontainer_runtime.harness_manager import HarnessManager
```

Change `__init__` and `handle`:

```python
    def __init__(
        self, runner: ClaudeCodeRunner, harness_manager: HarnessManager | None = None
    ) -> None:
        self._runner = runner
        self._sessions = RunningSessions()
        self._harness_manager = harness_manager
```

In `handle`, before the final `else`:

```python
        elif command.type == CommandType.AUTHENTICATE_HARNESS:
            await self._authenticate_harness(command, emit)
```

Add the method:

```python
    async def _authenticate_harness(self, command: Command, emit: EmitFn) -> None:
        if self._harness_manager is None:
            logger.info("authenticate_harness received but no harness manager wired")
            return
        payload = command.payload or {}
        harness = payload.get("harness", "")
        status = await self._harness_manager.authenticate(harness, payload.get("credentials") or {})
        await emit(
            RuntimeEvent(
                event_type=EventType.HARNESS_STATUS,
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                payload={
                    "harness": status.name,
                    "installed": status.installed,
                    "authenticated": status.authenticated,
                },
            )
        )
```

- [ ] **Step 4: Run tests to verify pass (new + existing handler tests)**

Run: `uv run pytest tests/devcontainer_runtime/test_command_handler_harness.py tests/devcontainer_runtime/test_command_handler.py -q`
Expected: PASS (new test + all existing handler tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/command_handler.py tests/devcontainer_runtime/test_command_handler_harness.py
git commit -m "feat(runtime): handle authenticate_harness -> harness_status event"
```

---

### Task 9: DelegatedRunManager (spawn / status / result / stop)

**Files:**
- Create: `src/vibing_devcontainer_runtime/delegated_runs.py`
- Test: `tests/devcontainer_runtime/test_delegated_runs.py` (create)

**Interfaces:**
- Consumes: `dict[str, HarnessAdapter]`, `HarnessProcessFactory`, `HarnessProcess`/`CompletedCommand`, `EmitFn` (`Callable[[RuntimeEvent], Awaitable[None]]`), `EventType`, `RuntimeEventSource`.
- Produces: `DelegatedRunManager(adapters, factory, emit, *, devcontainer_id, workspace, max_concurrent=4)` with:
  - `async spawn(harness, model, prompt, *, cwd=None, detached=False) -> dict` — blocking returns `{"run_id", "status": "completed"|"failed", "result"|"error"}`; detached returns `{"run_id", "status": "running"}`. Raises `KeyError` (unknown harness), `RuntimeError` ("not authenticated" / "at capacity").
  - `get_status(run_id) -> dict` / `get_result(run_id) -> dict` / `async stop(run_id) -> dict`.
  - Run ids are `f"run-{n}"` from a monotonic counter (deterministic for tests; no Date/random).
  - Emits `DELEGATED_RUN_STARTED` (payload `{"delegated_run_id","harness","model"}`), then `DELEGATED_RUN_COMPLETED` (`{"delegated_run_id","result"}`) or `DELEGATED_RUN_FAILED` (`{"delegated_run_id","exit_code","stderr_tail"}`).
- Consumed by: Task 10 (MCP tools).

- [ ] **Step 1: Write the failing test**

```python
# tests/devcontainer_runtime/test_delegated_runs.py
import asyncio
from typing import Any

import pytest

from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager
from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.process import CompletedCommand, HarnessProcess
from vibing_protocol import RuntimeEvent


class FakeAdapter(HarnessAdapter):
    def __init__(self, authed: bool = True) -> None:
        self.name = "codex"
        self._authed = authed

    async def is_installed(self) -> bool:
        return True

    async def install(self) -> None: ...

    async def is_authenticated(self) -> bool:
        return self._authed

    def write_credentials(self, blob: dict[str, Any]) -> None: ...

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return ["codex", "exec", prompt]

    def spawn_env(self) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()


class ScriptedProcess(HarnessProcess):
    def __init__(self, result: CompletedCommand, gate: asyncio.Event | None = None) -> None:
        self._result = result
        self._gate = gate
        self.terminated = False

    async def wait(self) -> CompletedCommand:
        if self._gate is not None:
            await self._gate.wait()
        return self._result

    async def terminate(self) -> None:
        self.terminated = True
        if self._gate is not None:
            self._gate.set()


def collector():
    events: list[RuntimeEvent] = []

    async def emit(e: RuntimeEvent) -> None:
        events.append(e)

    return events, emit


def test_blocking_spawn_returns_result_and_emits_lifecycle():
    events, emit = collector()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "the answer\n", ""))

    mgr = DelegatedRunManager(
        {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
    )
    out = asyncio.run(mgr.spawn("codex", "gpt-5.4", "do it"))
    assert out == {"run_id": "run-1", "status": "completed", "result": "the answer"}
    types = [e.event_type for e in events]
    assert types == ["delegated_run_started", "delegated_run_completed"]
    assert events[0].payload == {"delegated_run_id": "run-1", "harness": "codex", "model": "gpt-5.4"}


def test_spawn_uses_workspace_as_default_cwd_and_spawn_env():
    events, emit = collector()
    captured = {}

    def factory(argv, cwd, env):
        captured["cwd"] = cwd
        captured["env"] = env
        return ScriptedProcess(CompletedCommand(0, "ok", ""))

    mgr = DelegatedRunManager(
        {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
    )
    asyncio.run(mgr.spawn("codex", "m", "p"))
    assert captured["cwd"] == "/ws"


def test_failed_run_emits_failed_event():
    events, emit = collector()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(2, "", "boom"))

    mgr = DelegatedRunManager(
        {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
    )
    out = asyncio.run(mgr.spawn("codex", "m", "p"))
    assert out["status"] == "failed"
    assert events[-1].event_type == "delegated_run_failed"
    assert events[-1].payload["exit_code"] == 2


def test_unauthenticated_harness_raises():
    _, emit = collector()
    mgr = DelegatedRunManager(
        {"codex": FakeAdapter(authed=False)}, lambda *a: None, emit,
        devcontainer_id="dc-1", workspace="/ws",
    )
    with pytest.raises(RuntimeError, match="not authenticated"):
        asyncio.run(mgr.spawn("codex", "m", "p"))


def test_detached_spawn_returns_running_then_pollable():
    events, emit = collector()
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "late result", ""), gate=gate)

    async def scenario():
        mgr = DelegatedRunManager(
            {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
        )
        started = await mgr.spawn("codex", "m", "p", detached=True)
        assert started == {"run_id": "run-1", "status": "running"}
        assert mgr.get_status("run-1")["status"] == "running"
        gate.set()
        await mgr.wait_all()
        assert mgr.get_status("run-1")["status"] == "completed"
        assert mgr.get_result("run-1")["result"] == "late result"

    asyncio.run(scenario())


def test_capacity_cap_rejects_when_full():
    events, emit = collector()
    gate = asyncio.Event()

    def factory(argv, cwd, env):
        return ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    async def scenario():
        mgr = DelegatedRunManager(
            {"codex": FakeAdapter()}, factory, emit,
            devcontainer_id="dc-1", workspace="/ws", max_concurrent=1,
        )
        await mgr.spawn("codex", "m", "p", detached=True)
        with pytest.raises(RuntimeError, match="at capacity"):
            await mgr.spawn("codex", "m", "p", detached=True)
        gate.set()
        await mgr.wait_all()

    asyncio.run(scenario())


def test_stop_terminates_detached_run():
    events, emit = collector()
    gate = asyncio.Event()
    proc = ScriptedProcess(CompletedCommand(0, "x", ""), gate=gate)

    def factory(argv, cwd, env):
        return proc

    async def scenario():
        mgr = DelegatedRunManager(
            {"codex": FakeAdapter()}, factory, emit, devcontainer_id="dc-1", workspace="/ws"
        )
        await mgr.spawn("codex", "m", "p", detached=True)
        out = await mgr.stop("run-1")
        assert out["status"] == "stopped"
        assert proc.terminated is True
        await mgr.wait_all()

    asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_delegated_runs.py -q`
Expected: FAIL — `ModuleNotFoundError: ...delegated_runs`.

- [ ] **Step 3: Create `delegated_runs.py`**

```python
"""DelegatedRunManager: runs managed harnesses unattended (ADR-0013).

Concurrent up to a cap; each run is a HarnessProcess tracked by run id. Emits
delegated_run_started then _completed/_failed runtime events. Runs are not durable —
results live in memory for the process lifetime.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from logzero import logger
from vibing_protocol import EventType, RuntimeEvent, RuntimeEventSource

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.process import HarnessProcess, HarnessProcessFactory

_SOURCE = RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT
EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


@dataclass
class _Run:
    run_id: str
    harness: str
    model: str
    status: str = "running"  # running | completed | failed | stopped
    result: str = ""
    error: dict[str, Any] = field(default_factory=dict)
    process: HarnessProcess | None = None
    task: asyncio.Task[None] | None = None


class DelegatedRunManager:
    def __init__(
        self,
        adapters: dict[str, HarnessAdapter],
        factory: HarnessProcessFactory,
        emit: EmitFn,
        *,
        devcontainer_id: str,
        workspace: str,
        max_concurrent: int = 4,
    ) -> None:
        self._adapters = adapters
        self._factory = factory
        self._emit = emit
        self._devcontainer_id = devcontainer_id
        self._workspace = workspace
        self._max = max_concurrent
        self._runs: dict[str, _Run] = {}
        self._counter = 0

    def _active(self) -> int:
        return sum(1 for r in self._runs.values() if r.status == "running")

    async def spawn(
        self,
        harness: str,
        model: str,
        prompt: str,
        *,
        cwd: str | None = None,
        detached: bool = False,
    ) -> dict[str, Any]:
        adapter = self._adapters[harness]  # KeyError on unknown harness
        if not await adapter.is_authenticated():
            raise RuntimeError(f"harness {harness} is not authenticated")
        if self._active() >= self._max:
            raise RuntimeError("delegated runs at capacity")

        self._counter += 1
        run = _Run(run_id=f"run-{self._counter}", harness=harness, model=model)
        self._runs[run.run_id] = run

        argv = adapter.build_spawn_argv(model, prompt)
        run.process = self._factory(argv, cwd or self._workspace, adapter.spawn_env())
        await self._emit(
            RuntimeEvent(
                event_type=EventType.DELEGATED_RUN_STARTED,
                source=_SOURCE,
                devcontainer_id=self._devcontainer_id,
                payload={"delegated_run_id": run.run_id, "harness": harness, "model": model},
            )
        )

        if detached:
            run.task = asyncio.create_task(self._await_run(run, adapter))
            return {"run_id": run.run_id, "status": "running"}
        await self._await_run(run, adapter)
        if run.status == "completed":
            return {"run_id": run.run_id, "status": "completed", "result": run.result}
        return {"run_id": run.run_id, "status": "failed", "error": run.error}

    async def _await_run(self, run: _Run, adapter: HarnessAdapter) -> None:
        assert run.process is not None
        try:
            result = await run.process.wait()
        except asyncio.CancelledError:
            run.status = "stopped"
            raise
        if result.returncode == 0:
            run.status = "completed"
            run.result = adapter.extract_result(result.stdout)
            await self._emit(
                RuntimeEvent(
                    event_type=EventType.DELEGATED_RUN_COMPLETED,
                    source=_SOURCE,
                    devcontainer_id=self._devcontainer_id,
                    payload={"delegated_run_id": run.run_id, "result": run.result},
                )
            )
        else:
            run.status = "failed"
            run.error = {"exit_code": result.returncode, "stderr_tail": result.stderr[-4000:]}
            await self._emit(
                RuntimeEvent(
                    event_type=EventType.DELEGATED_RUN_FAILED,
                    source=_SOURCE,
                    devcontainer_id=self._devcontainer_id,
                    payload={"delegated_run_id": run.run_id, **run.error},
                )
            )

    def _get(self, run_id: str) -> _Run:
        return self._runs[run_id]  # KeyError on unknown run

    def get_status(self, run_id: str) -> dict[str, Any]:
        run = self._get(run_id)
        return {"run_id": run_id, "status": run.status}

    def get_result(self, run_id: str) -> dict[str, Any]:
        run = self._get(run_id)
        return {"run_id": run_id, "status": run.status, "result": run.result, "error": run.error}

    async def stop(self, run_id: str) -> dict[str, Any]:
        run = self._get(run_id)
        if run.task is not None and not run.task.done():
            run.task.cancel()
            try:
                await run.task
            except (asyncio.CancelledError, Exception):
                pass
        if run.process is not None:
            await run.process.terminate()
        run.status = "stopped"
        return {"run_id": run_id, "status": "stopped"}

    async def wait_all(self) -> None:
        tasks = [r.task for r in self._runs.values() if r.task is not None and not r.task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/devcontainer_runtime/test_delegated_runs.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/delegated_runs.py tests/devcontainer_runtime/test_delegated_runs.py
git commit -m "feat(runtime): DelegatedRunManager (concurrent capped runs + events)"
```

---

### Task 10: MCP server (`mcp_server.py`)

**Files:**
- Modify: `pyproject.toml` (via `uv add mcp`)
- Create: `src/vibing_devcontainer_runtime/mcp_server.py`
- Test: `tests/devcontainer_runtime/test_mcp_server.py` (create)

**Interfaces:**
- Consumes: `HarnessManager` (Task 7), `DelegatedRunManager` (Task 9), `FastMCP`.
- Produces: `build_mcp_server(harness_manager, delegated_runs, *, host="127.0.0.1", port=8848) -> FastMCP`. Registers tools: `list_harnesses()`, `spawn(harness, model, prompt, detached=False, cwd=None)`, `get_status(run_id)`, `get_result(run_id)`, `stop(run_id)`. Each delegates to the managers and returns plain JSON-able dicts/lists.

- [ ] **Step 1: Add the dependency**

Run: `uv add mcp`
Expected: `pyproject.toml` gains `mcp` under `[project].dependencies`; `uv.lock` updates. (Load the `uv` skill if unsure.)

- [ ] **Step 2: Write the failing test**

The tools are registered on a FastMCP; test them by reading them back via the SDK's async introspection (`mcp.list_tools()`) and invoking via `mcp.call_tool(name, args)`, which returns `(content, structured_result)`.

```python
# tests/devcontainer_runtime/test_mcp_server.py
import asyncio
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessStatus
from vibing_devcontainer_runtime.mcp_server import build_mcp_server


class FakeHarnessManager:
    async def list_statuses(self) -> list[HarnessStatus]:
        return [HarnessStatus("codex", True, True), HarnessStatus("cursor", False, False)]


class FakeDelegatedRuns:
    def __init__(self) -> None:
        self.spawned: list[tuple[Any, ...]] = []

    async def spawn(self, harness, model, prompt, *, cwd=None, detached=False):
        self.spawned.append((harness, model, prompt, cwd, detached))
        return {"run_id": "run-1", "status": "completed", "result": "ok"}

    def get_status(self, run_id):
        return {"run_id": run_id, "status": "running"}

    def get_result(self, run_id):
        return {"run_id": run_id, "status": "completed", "result": "ok", "error": {}}

    async def stop(self, run_id):
        return {"run_id": run_id, "status": "stopped"}


def test_tools_are_registered():
    mcp = build_mcp_server(FakeHarnessManager(), FakeDelegatedRuns())
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_harnesses", "spawn", "get_status", "get_result", "stop"} <= names


def test_list_harnesses_returns_statuses():
    mcp = build_mcp_server(FakeHarnessManager(), FakeDelegatedRuns())
    _content, result = asyncio.run(mcp.call_tool("list_harnesses", {}))
    # structured tool output wraps a list under "result"
    harnesses = result["result"] if isinstance(result, dict) and "result" in result else result
    names = {h["name"] for h in harnesses}
    assert names == {"codex", "cursor"}


def test_spawn_forwards_args_and_returns_outcome():
    runs = FakeDelegatedRuns()
    mcp = build_mcp_server(FakeHarnessManager(), runs)
    _content, result = asyncio.run(
        mcp.call_tool("spawn", {"harness": "codex", "model": "gpt-5.4", "prompt": "go"})
    )
    assert runs.spawned == [("codex", "gpt-5.4", "go", None, False)]
    assert result["status"] == "completed" and result["result"] == "ok"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_mcp_server.py -q`
Expected: FAIL — `ModuleNotFoundError: ...mcp_server`.

- [ ] **Step 4: Create `mcp_server.py`**

```python
"""build_mcp_server: the in-container MCP server the main harness calls (ADR-0011/0013).

Streamable-HTTP, stateless, JSON responses. Tools delegate to HarnessManager (status)
and DelegatedRunManager (spawn/status/result/stop). The runtime owns its lifecycle
(cli.py runs it alongside the Control Plane WebSocket client).
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager
from vibing_devcontainer_runtime.harness_manager import HarnessManager


def build_mcp_server(
    harness_manager: HarnessManager,
    delegated_runs: DelegatedRunManager,
    *,
    host: str = "127.0.0.1",
    port: int = 8848,
) -> FastMCP:
    mcp = FastMCP("vibing-harness", host=host, port=port, stateless_http=True, json_response=True)

    @mcp.tool()
    async def list_harnesses() -> list[dict[str, Any]]:
        """List managed coding harnesses with installed/authenticated status."""
        statuses = await harness_manager.list_statuses()
        return [
            {"name": s.name, "installed": s.installed, "authenticated": s.authenticated}
            for s in statuses
        ]

    @mcp.tool()
    async def spawn(
        harness: str, model: str, prompt: str, detached: bool = False, cwd: str | None = None
    ) -> dict[str, Any]:
        """Spawn a Delegated Run. Blocks for the result unless detached=true."""
        return await delegated_runs.spawn(harness, model, prompt, cwd=cwd, detached=detached)

    @mcp.tool()
    def get_status(run_id: str) -> dict[str, Any]:
        """Get the status of a detached Delegated Run."""
        return delegated_runs.get_status(run_id)

    @mcp.tool()
    def get_result(run_id: str) -> dict[str, Any]:
        """Get the result of a finished Delegated Run."""
        return delegated_runs.get_result(run_id)

    @mcp.tool()
    async def stop(run_id: str) -> dict[str, Any]:
        """Stop a running Delegated Run."""
        return await delegated_runs.stop(run_id)

    return mcp
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/devcontainer_runtime/test_mcp_server.py -q`
Expected: PASS (3 passed). If `call_tool`'s structured-result shape differs in the installed `mcp` version, adjust the test's unwrap (the `_content` first element also carries the JSON) — the tool functions themselves are correct.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/vibing_devcontainer_runtime/mcp_server.py tests/devcontainer_runtime/test_mcp_server.py
git commit -m "feat(runtime): MCP server exposing list_harnesses/spawn/status/result/stop"
```

---

### Task 11: CLI — run channel client + MCP server concurrently

**Files:**
- Modify: `src/vibing_devcontainer_runtime/cli.py`
- Test: `tests/devcontainer_runtime/test_cli.py` (extend)

**Interfaces:**
- Consumes: `RuntimeChannelClient` (`run()` async, `on_request`), `AgentCommandHandler`, `HarnessManager`, `DelegatedRunManager`, `build_adapters`, `build_mcp_server`, `real_process_factory`.
- Produces: `serve(...)` now also constructs the managers + MCP server and runs `client.run()` and `uvicorn` serve of `mcp.streamable_http_app()` concurrently via `asyncio.gather`. New options `--mcp-host` (default `127.0.0.1`), `--mcp-port` (default `8848`), `--workspace` (default `.`). Extract the async body into `async def _serve_async(...)` for testability.

- [ ] **Step 1: Write the failing test**

Existing `test_cli.py` monkeypatches the client; extend it to assert the MCP server + managers are wired and both run concurrently. Add:

```python
# tests/devcontainer_runtime/test_cli.py  (add to existing file)
from vibing_devcontainer_runtime import cli as cli_module


def test_serve_builds_managers_and_runs_both(monkeypatch):
    built = {}

    class FakeClient:
        def __init__(self, url, register, handler):
            built["handler_owner"] = handler.__self__  # AgentCommandHandler instance
            self._requests = {}

        def on_request(self, message_type, respond):
            self._requests[message_type] = respond

        async def run(self):
            built["client_ran"] = True

    async def fake_serve_http(self):  # FastMCP.run_streamable_http_async stand-in
        built["mcp_ran"] = True

    monkeypatch.setattr(cli_module, "RuntimeChannelClient", FakeClient)
    monkeypatch.setattr(
        cli_module.FastMCP, "run_streamable_http_async", fake_serve_http, raising=True
    )

    cli_module._serve_blocking("ws://x", "dc-1", "127.0.0.1", 8848, ".")

    assert built["client_ran"] is True
    assert built["mcp_ran"] is True
    # the command handler got a harness manager wired
    assert built["handler_owner"]._harness_manager is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_cli.py -q`
Expected: FAIL — `AttributeError: module 'vibing_devcontainer_runtime.cli' has no attribute '_serve_blocking'`.

- [ ] **Step 3: Rewrite `cli.py`**

```python
"""Command-line entry point for the Devcontainer Runtime Agent.

Connects to the Control Plane agent channel, registers with a devcontainer_id, and runs
two concurrent jobs in one asyncio loop (ADR-0011): the Command/event WebSocket client
(Agent Sessions) and the MCP server the main harness calls to spawn Delegated Runs.
"""

import asyncio
from pathlib import Path

import typer
from logzero import logger
from mcp.server.fastmcp import FastMCP
from vibing_protocol import RegisterEnvelope, RuntimeEventSource
from vibing_runtime_client import RuntimeChannelClient

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner
from vibing_devcontainer_runtime.command_handler import AgentCommandHandler, _make_emit
from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager
from vibing_devcontainer_runtime.harness.process import real_process_factory
from vibing_devcontainer_runtime.harness.registry import build_adapters
from vibing_devcontainer_runtime.harness_manager import HarnessManager
from vibing_devcontainer_runtime.mcp_server import build_mcp_server
from vibing_devcontainer_runtime.transcript import TranscriptReader

DEFAULT_CONTROL_PLANE_URL = "ws://host.docker.internal:8000/api/v1/runtime/agent/ws"

cli = typer.Typer(
    add_completion=False,
    help="Devcontainer Runtime Agent: Agent Sessions + harness delegation MCP server.",
)


async def _serve_async(
    control_plane_url: str, devcontainer_id: str, mcp_host: str, mcp_port: int, workspace: str
) -> None:
    adapters = build_adapters(real_process_factory, Path.home())
    harness_manager = HarnessManager(adapters)

    register = RegisterEnvelope(
        source=RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT, devcontainer_id=devcontainer_id
    )
    handler = AgentCommandHandler(ClaudeCodeRunner(), harness_manager=harness_manager)
    client = RuntimeChannelClient(control_plane_url, register, handler.handle)
    client.on_request("transcript_request", TranscriptReader().respond)

    # Delegated runs emit over the same channel; reuse the client's send via a forwarding emit.
    emit = _make_emit(client.send_envelope)
    delegated_runs = DelegatedRunManager(
        adapters,
        real_process_factory,
        emit,
        devcontainer_id=devcontainer_id,
        workspace=workspace,
    )
    mcp = build_mcp_server(harness_manager, delegated_runs, host=mcp_host, port=mcp_port)

    await asyncio.gather(
        client.run(),
        mcp.run_streamable_http_async(host=mcp_host, port=mcp_port),
    )


def _serve_blocking(
    control_plane_url: str, devcontainer_id: str, mcp_host: str, mcp_port: int, workspace: str
) -> None:
    try:
        asyncio.run(
            _serve_async(control_plane_url, devcontainer_id, mcp_host, mcp_port, workspace)
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


@cli.callback(invoke_without_command=True)
def serve(
    control_plane_url: str = typer.Option(DEFAULT_CONTROL_PLANE_URL, help="Control Plane WS URL"),
    devcontainer_id: str = typer.Option(..., help="Unique ID of this devcontainer"),
    mcp_host: str = typer.Option("127.0.0.1", help="MCP server bind host"),
    mcp_port: int = typer.Option(8848, help="MCP server bind port"),
    workspace: str = typer.Option(".", help="Default working dir for Delegated Runs"),
) -> None:
    """Connect to the Control Plane and serve the harness-delegation MCP server."""
    logger.info(
        "Starting devcontainer runtime agent (cp=%s, dc=%s, mcp=%s:%d, ws=%s)",
        control_plane_url, devcontainer_id, mcp_host, mcp_port, workspace,
    )
    _serve_blocking(control_plane_url, devcontainer_id, mcp_host, mcp_port, workspace)


def main() -> None:
    cli()
```

> **Dependency note (Task 11a):** `_serve_async` calls `client.send_envelope`, which does not yet exist — `RuntimeChannelClient` only exposes `send` *inside* a session via the handler. Add a small public `send_envelope(envelope: BaseModel)` to `RuntimeChannelClient` that sends over the current `self._ws` (no-op + warning if disconnected). This is the one runtime_client change. Do it as Step 3a below before running the CLI test.

- [ ] **Step 3a: Add `send_envelope` to the channel client**

In `src/vibing_runtime_client/client.py`, add a method to `RuntimeChannelClient`:

```python
    async def send_envelope(self, envelope: BaseModel) -> None:
        """Send an envelope outside the command-handler path (e.g. Delegated Run events)."""
        ws = self._ws
        if ws is None:
            logger.warning("Dropping %s: runtime channel not connected", type(envelope).__name__)
            return
        await ws.send(json.dumps(envelope.model_dump()))
```

Add a focused test in `tests/runtime_client/test_runtime_channel_client.py`:

```python
def test_send_envelope_warns_and_noops_when_disconnected():
    from vibing_protocol import RegisterEnvelope
    from vibing_runtime_client.client import RuntimeChannelClient

    async def handler(cmd, send):
        return None

    client = RuntimeChannelClient("ws://x", RegisterEnvelope(), handler)
    import asyncio
    asyncio.run(client.send_envelope(RegisterEnvelope()))  # no ws -> no raise
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/devcontainer_runtime/test_cli.py tests/runtime_client/test_runtime_channel_client.py -q`
Expected: PASS (existing CLI tests + new wiring test + send_envelope test).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/cli.py src/vibing_runtime_client/client.py tests/devcontainer_runtime/test_cli.py tests/runtime_client/test_runtime_channel_client.py
git commit -m "feat(runtime): serve MCP delegation server alongside the Command channel"
```

---

### Task 12: Docs — package CLAUDE.md coherence

**Files:**
- Modify: `src/vibing_devcontainer_runtime/CLAUDE.md`
- Modify: `src/vibing_protocol/CLAUDE.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `vibing_devcontainer_runtime/CLAUDE.md`**

Add to the `## Files` list:

```markdown
- `harness/`: per-harness adapters (`base` contract, `codex`, `cursor`), the `process` subprocess
  seam, and `registry.build_adapters`. The only place pinned to each harness's CLI flags + cred path.
- `harness_manager.py`: drives adapters for `authenticate_harness` + status (ADR-0012).
- `delegated_runs.py`: `DelegatedRunManager` — concurrent capped unattended runs; emits
  delegated_run_started/completed/failed (ADR-0013).
- `mcp_server.py`: `build_mcp_server` — streamable-HTTP MCP server (`list_harnesses`/`spawn`/
  `get_status`/`get_result`/`stop`) the main harness calls (ADR-0011).
```

Add to `## Context`: `- cli serves the Command channel + MCP server (default 127.0.0.1:8848) concurrently.`

- [ ] **Step 2: Update `vibing_protocol/CLAUDE.md`**

In the `commands.py` / `runtime_events.py` bullets, note the new members: `AUTHENTICATE_HARNESS`; `HARNESS_STATUS`, `DELEGATED_RUN_STARTED/COMPLETED/FAILED` (payload carries `delegated_run_id`, `harness`).

- [ ] **Step 3: Commit**

```bash
git add src/vibing_devcontainer_runtime/CLAUDE.md src/vibing_protocol/CLAUDE.md
git commit -m "docs(runtime): document harness management + MCP delegation modules"
```

---

### Task 13: Full verification gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full check suite from repo root**

Run:
```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q
```
Expected: all green. Fix any ruff/mypy findings inline (e.g. unused imports, missing annotations) and re-run. Do **not** weaken types to pass mypy.

- [ ] **Step 2: Manual smoke (optional, requires a real container with codex/cursor)**

In a devcontainer with network egress: run `vibing devcontainer-runtime --devcontainer-id smoke --mcp-port 8848` (it will try to reach the Control Plane; the MCP server still binds). From another shell in the container: `curl -s 127.0.0.1:8848/mcp` should respond (MCP handshake), confirming the server is up. Verify `codex --help` / `cursor-agent --help` flags match the adapters; adjust adapter argv if the installed versions differ.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A && git commit -m "chore(runtime): verification fixups"
```

---

## Self-Review

**Spec coverage (ADR-0011/0012/0013, runtime side):**
- Check installed/authenticated → Tasks 4-7 (adapters + `HarnessManager.list_statuses`) + Task 10 (`list_harnesses` MCP tool). ✓
- Install on demand → adapters' `install()`, invoked by `HarnessManager.authenticate` (Task 7). ✓
- Authenticate from a credential blob → Task 8 (`authenticate_harness` command → `HARNESS_STATUS` event). ✓
- MCP server, runtime-owned HTTP, stable localhost URL → Tasks 10-11. ✓
- `spawn` blocking + detached; `get_status`/`get_result`/`stop` → Tasks 9-10. ✓
- Delegated Runs: unattended bypass (adapter argv), concurrent capped, workspace cwd, observable via runtime events → Task 9. ✓
- Coexists with Agent Session path (untouched; `harness_manager` optional) → Tasks 8, 11. ✓
- **Deferred (separate plan):** host-capture command, Control Plane credential storage, event projections/UI. Documented under "Out of scope." ✓

**Placeholder scan:** every code step contains complete code; CLI flags are concrete (with a verify-against-`--help` note where research flagged uncertainty — cursor cred storage, model names). No TBDs.

**Type consistency:** `HarnessProcessFactory` signature `(argv, cwd, env)` is used identically in adapters, registry, delegated_runs, and cli. `HarnessStatus(name, installed, authenticated)` and the `{"harness","installed","authenticated"}` payload shape match across Tasks 7-8-10. `spawn(...)` keyword args (`cwd`, `detached`) match across Tasks 9-10-11. `emit`/`EmitFn` (`RuntimeEvent -> Awaitable[None]`) matches `_make_emit` in command_handler (Task 9 reuses it in Task 11).

---

## Follow-up plan (separate subsystem — not built here)

**Control Plane credential pipeline & host capture.** Tasks: (1) `vibing` host-capture command reading a harness's on-disk auth file (`~/.codex/auth.json`, cursor API key) into the Control Plane; (2) credential storage (repository + schema, plaintext per ADR-0012); (3) API/CLI to emit `authenticate_harness` to a devcontainer; (4) optional projections of `harness_status` + `delegated_run_*` events for the web UI. This plan's runtime already *handles* (3) and *emits* (4)'s events, so the follow-up is purely Control-Plane-side.
