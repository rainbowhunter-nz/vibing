# Control-Plane-Owned Harness Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Coding Harness install/authenticate/status from the Devcontainer Runtime to the Control Plane (executed via `devcontainer exec`), behind a shared `vibing_harness` package, and delete the entire CP→Runtime Command direction.

**Architecture:** A new dependency-light `vibing_harness` package holds all per-harness knowledge as behavior over an injected `Executor` protocol (`run`/`read`/`write`). The Control Plane supplies a `DevcontainerExecutor` (host `devcontainer exec`) and owns install/auth/status; the Runtime supplies a `LocalExecutor` (in-container subprocess) used only for the MCP `list_harnesses` tool and Delegated Run spawning. The runtime WebSocket becomes outbound-only (`register` + `delegated_runs`); `Command`, `CommandEnvelope`, and `HarnessStatusEnvelope` are removed. See `docs/adr/0019-the-control-plane-owns-harness-setup-via-devcontainer-exec-and-the-runtime-is-delegation-only.md`.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, asyncio subprocess, pytest; React + TypeScript + MSW (frontend).

## Global Constraints

- Python ≥ 3.13; `uv` manages deps — never hand-edit `[project.dependencies]`; add packages to `[tool.uv.build-backend].module-name`.
- `vibing_harness` deps: **stdlib + Pydantic only** (matches `vibing_protocol`). No FastAPI, no container libraries.
- Ruff line-length 100. All Python passes: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Comparison of harness names uses plain strings (harness ids: `"codex"`, `"cursor"`).
- The CP installs/checks via `devcontainer exec` (remoteUser-correct). **Never** raw `docker exec` for harness ops (root → wrong npm prefix).
- Credential blob shape is unchanged: `{"auth_json": {...}}` (codex) or `{"api_key": "..."}` (cursor).
- Commit after every task. Each task leaves the full suite green.

---

## File Structure

**New package `src/vibing_harness/`:**
- `__init__.py` — public exports.
- `executor.py` — `Executor` Protocol + `CommandResult`.
- `base.py` — `HarnessStatus`, `HarnessDescriptor` ABC.
- `descriptors/codex.py`, `descriptors/cursor.py` — the two harnesses.
- `registry.py` — `descriptors() -> dict[str, HarnessDescriptor]`.

**Control Plane (`src/vibing_api/`):**
- Create `core/devcontainer_executor.py` — `DevcontainerExecutor` (Executor over `devcontainer exec`) + PIPE/stream/stdin runner.
- Create `core/harness_service.py` — install/authenticate/status compute + cache + SSE.
- Modify `api/routes/harnesses.py` — streaming install/auth, `refresh`, cached GET.
- Modify `api/routes/runtime.py`, `core/runtime_channel.py`, `core/runtime_intake.py`, `core/live_state.py` — drop Command + harness_status.

**Runtime (`src/vibing_devcontainer_runtime/`):**
- Create `local_executor.py` — `LocalExecutor`.
- Modify `mcp_server.py`, `delegated_runs.py`, `cli.py`, `runtime_client.py`.
- Delete `harness/` (whole dir), `harness_manager.py`, `command_handler.py`.

**Protocol (`src/vibing_protocol/`):**
- Delete `commands.py`; trim `messages.py` + `__init__.py`.

**Frontend (`apps/web/`):** `HarnessList.tsx`, `lib/api/endpoints.ts`, `lib/api/types.ts`, mock handlers.

---

## Task 1: `vibing_harness` package skeleton — Executor + base

**Files:**
- Modify: `pyproject.toml:36-42` (add module)
- Create: `src/vibing_harness/__init__.py`
- Create: `src/vibing_harness/executor.py`
- Create: `src/vibing_harness/base.py`
- Test: `tests/harness/__init__.py`, `tests/harness/fakes.py`, `tests/harness/test_base.py`

**Interfaces:**
- Produces:
  - `CommandResult(returncode: int, stdout: str, stderr: str)` (frozen dataclass)
  - `class Executor(Protocol)`: `async run(argv: list[str]) -> CommandResult`; `async read(path: str) -> bytes | None`; `async write(path: str, data: bytes, mode: int = 0o600) -> None`
  - `HarnessStatus(name: str, installed: bool, authenticated: bool)` (frozen dataclass)
  - `class HarnessDescriptor(ABC)`: attr `name: str`; `async is_installed(ex)`, `async install(ex)`, `async is_authenticated(ex)`, `async write_credentials(ex, blob: dict)`, `build_spawn_argv(model, prompt) -> list[str]`, `async spawn_env(ex) -> dict[str, str]`, `extract_result(stdout) -> str`; concrete `async status(ex) -> HarnessStatus`.

- [ ] **Step 1: Add the package to the build backend**

In `pyproject.toml`, edit the `module-name` list:

```toml
[tool.uv.build-backend]
module-name = [
    "vibing_api",
    "vibing_devcontainer_runtime",
    "vibing_cli",
    "vibing_protocol",
    "vibing_harness",
]
```

- [ ] **Step 2: Write `executor.py`**

```python
"""Executor: the seam each consumer implements to run commands and read/write files
in a harness's environment. The Control Plane runs them via `devcontainer exec`; the
Runtime runs them as local subprocess + direct file IO. Descriptors are written against
this protocol and never execute anything themselves."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class Executor(Protocol):
    async def run(self, argv: list[str]) -> CommandResult: ...
    async def read(self, path: str) -> bytes | None: ...
    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None: ...
```

- [ ] **Step 3: Write `base.py`**

```python
"""HarnessDescriptor: per-harness knowledge as behaviour over an injected Executor.
The single home for a harness's binary, install/check/auth commands, credential path
and format, spawn argv/env, and result extraction. No execution context of its own."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from vibing_harness.executor import Executor


@dataclass(frozen=True)
class HarnessStatus:
    name: str
    installed: bool
    authenticated: bool


class HarnessDescriptor(ABC):
    name: str

    @abstractmethod
    async def is_installed(self, ex: Executor) -> bool: ...

    @abstractmethod
    async def install(self, ex: Executor) -> None: ...

    @abstractmethod
    async def is_authenticated(self, ex: Executor) -> bool: ...

    @abstractmethod
    async def write_credentials(self, ex: Executor, blob: dict) -> None: ...

    @abstractmethod
    def build_spawn_argv(self, model: str, prompt: str) -> list[str]: ...

    @abstractmethod
    async def spawn_env(self, ex: Executor) -> dict[str, str]: ...

    @abstractmethod
    def extract_result(self, stdout: str) -> str: ...

    async def status(self, ex: Executor) -> HarnessStatus:
        installed = await self.is_installed(ex)
        authenticated = await self.is_authenticated(ex) if installed else False
        return HarnessStatus(name=self.name, installed=installed, authenticated=authenticated)
```

- [ ] **Step 4: Write `__init__.py`**

```python
from vibing_harness.base import HarnessDescriptor, HarnessStatus
from vibing_harness.executor import CommandResult, Executor

__all__ = ["CommandResult", "Executor", "HarnessDescriptor", "HarnessStatus"]
```

- [ ] **Step 5: Write the test fake + base test**

`tests/harness/__init__.py`: empty file.

`tests/harness/fakes.py`:

```python
"""FakeExecutor: an in-memory Executor for descriptor tests. `run` returns scripted
results keyed by argv[0] (or a default); read/write hit an in-memory filesystem."""

from vibing_harness.executor import CommandResult


class FakeExecutor:
    def __init__(self, results: dict[str, CommandResult] | None = None) -> None:
        self._results = results or {}
        self.files: dict[str, bytes] = {}
        self.modes: dict[str, int] = {}
        self.runs: list[list[str]] = []

    async def run(self, argv: list[str]) -> CommandResult:
        self.runs.append(argv)
        return self._results.get(argv[0], CommandResult(0, "", ""))

    async def read(self, path: str) -> bytes | None:
        return self.files.get(path)

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        self.files[path] = data
        self.modes[path] = mode
```

`tests/harness/test_base.py`:

```python
import asyncio

from vibing_harness import CommandResult, Executor, HarnessDescriptor, HarnessStatus
from tests.harness.fakes import FakeExecutor


class _Stub(HarnessDescriptor):
    name = "stub"

    def __init__(self, installed: bool, authed: bool) -> None:
        self._installed = installed
        self._authed = authed

    async def is_installed(self, ex: Executor) -> bool:
        return self._installed

    async def install(self, ex: Executor) -> None: ...

    async def is_authenticated(self, ex: Executor) -> bool:
        return self._authed

    async def write_credentials(self, ex: Executor, blob: dict) -> None: ...

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return []

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout


def test_status_skips_auth_check_when_not_installed():
    s = asyncio.run(_Stub(installed=False, authed=True).status(FakeExecutor()))
    assert s == HarnessStatus(name="stub", installed=False, authenticated=False)


def test_status_reports_auth_when_installed():
    s = asyncio.run(_Stub(installed=True, authed=True).status(FakeExecutor()))
    assert s == HarnessStatus(name="stub", installed=True, authenticated=True)


def test_command_result_is_frozen():
    r = CommandResult(0, "out", "err")
    assert (r.returncode, r.stdout, r.stderr) == (0, "out", "err")
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/harness -q`
Expected: PASS (3 tests).

- [ ] **Step 7: Lint, type-check, commit**

```bash
uv run ruff format src/vibing_harness tests/harness
uv run ruff check src tests && uv run mypy src
git add pyproject.toml src/vibing_harness tests/harness
git commit -m "feat(harness): add vibing_harness package (Executor + descriptor base)"
```

---

## Task 2: Port codex + cursor descriptors

**Files:**
- Create: `src/vibing_harness/descriptors/__init__.py` (empty)
- Create: `src/vibing_harness/descriptors/codex.py`
- Create: `src/vibing_harness/descriptors/cursor.py`
- Create: `src/vibing_harness/registry.py`
- Modify: `src/vibing_harness/__init__.py` (export `descriptors`)
- Test: `tests/harness/test_codex.py`, `tests/harness/test_cursor.py`, `tests/harness/test_registry.py`

**Interfaces:**
- Consumes: `Executor`, `CommandResult`, `HarnessDescriptor` (Task 1); `tests.harness.fakes.FakeExecutor`.
- Produces:
  - `CodexDescriptor()`, `CursorDescriptor()`.
  - `registry.descriptors() -> dict[str, HarnessDescriptor]` → `{"codex": ..., "cursor": ...}`.
  - Credential paths are **home-relative POSIX strings** resolved against `$HOME` by the executor: codex `.codex/auth.json`; cursor `.config/vibing-harness/cursor.json`.

- [ ] **Step 1: Write `descriptors/codex.py`**

```python
"""Codex CLI (`codex`) descriptor. Credential path is home-relative; the executor
resolves it against the harness env's $HOME."""

import json

from vibing_harness.base import HarnessDescriptor
from vibing_harness.executor import Executor

_BINARY = "codex"
_CRED_PATH = ".codex/auth.json"


class CodexDescriptor(HarnessDescriptor):
    name = "codex"

    async def is_installed(self, ex: Executor) -> bool:
        return (await ex.run([_BINARY, "--version"])).returncode == 0

    async def install(self, ex: Executor) -> None:
        await ex.run(["npm", "install", "-g", "@openai/codex"])

    async def is_authenticated(self, ex: Executor) -> bool:
        return (await ex.run([_BINARY, "login", "status"])).returncode == 0

    async def write_credentials(self, ex: Executor, blob: dict) -> None:
        await ex.write(_CRED_PATH, json.dumps(blob["auth_json"]).encode())

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [_BINARY, "exec", "--model", model,
                "--dangerously-bypass-approvals-and-sandbox", prompt]

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
```

- [ ] **Step 2: Write `descriptors/cursor.py`**

```python
"""Cursor CLI (`cursor-agent`) descriptor. Auth is an api-key persisted to our own
config file and injected as CURSOR_API_KEY at spawn (the documented automation path)."""

import json

from vibing_harness.base import HarnessDescriptor
from vibing_harness.executor import Executor

_BINARY = "cursor-agent"
_CRED_PATH = ".config/vibing-harness/cursor.json"
_INSTALL = "curl https://cursor.com/install -fsS | bash"


class CursorDescriptor(HarnessDescriptor):
    name = "cursor"

    async def is_installed(self, ex: Executor) -> bool:
        return (await ex.run([_BINARY, "--version"])).returncode == 0

    async def install(self, ex: Executor) -> None:
        await ex.run(["bash", "-c", _INSTALL])

    async def _api_key(self, ex: Executor) -> str:
        raw = await ex.read(_CRED_PATH)
        if raw is None:
            return ""
        return json.loads(raw).get("api_key", "")

    async def is_authenticated(self, ex: Executor) -> bool:
        return bool(await self._api_key(ex))

    async def write_credentials(self, ex: Executor, blob: dict) -> None:
        await ex.write(_CRED_PATH, json.dumps({"api_key": blob["api_key"]}).encode())

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [_BINARY, "-p", prompt, "--model", model, "--force", "--output-format", "text"]

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
        key = await self._api_key(ex)
        return {"CURSOR_API_KEY": key} if key else {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
```

- [ ] **Step 3: Write `registry.py`**

```python
"""descriptors(): name -> HarnessDescriptor. The managed-harness list lives here."""

from vibing_harness.base import HarnessDescriptor
from vibing_harness.descriptors.codex import CodexDescriptor
from vibing_harness.descriptors.cursor import CursorDescriptor


def descriptors() -> dict[str, HarnessDescriptor]:
    items: list[HarnessDescriptor] = [CodexDescriptor(), CursorDescriptor()]
    return {d.name: d for d in items}
```

- [ ] **Step 4: Export from `__init__.py`**

Append `descriptors` to the imports and `__all__`:

```python
from vibing_harness.base import HarnessDescriptor, HarnessStatus
from vibing_harness.executor import CommandResult, Executor
from vibing_harness.registry import descriptors

__all__ = [
    "CommandResult",
    "Executor",
    "HarnessDescriptor",
    "HarnessStatus",
    "descriptors",
]
```

- [ ] **Step 5: Write `tests/harness/test_codex.py`**

```python
import asyncio
import json

from vibing_harness import CommandResult
from vibing_harness.descriptors.codex import CodexDescriptor
from tests.harness.fakes import FakeExecutor


def test_is_installed_true_on_version_zero():
    ex = FakeExecutor({"codex": CommandResult(0, "codex 1.2.3", "")})
    assert asyncio.run(CodexDescriptor().is_installed(ex)) is True
    assert ex.runs[0] == ["codex", "--version"]


def test_is_installed_false_when_missing():
    ex = FakeExecutor({"codex": CommandResult(127, "", "not found")})
    assert asyncio.run(CodexDescriptor().is_installed(ex)) is False


def test_install_runs_npm_global():
    ex = FakeExecutor()
    asyncio.run(CodexDescriptor().install(ex))
    assert ex.runs[0] == ["npm", "install", "-g", "@openai/codex"]


def test_is_authenticated_uses_login_status():
    ex = FakeExecutor({"codex": CommandResult(0, "Logged in", "")})
    assert asyncio.run(CodexDescriptor().is_authenticated(ex)) is True
    assert ex.runs[0] == ["codex", "login", "status"]


def test_write_credentials_writes_home_relative_auth_json():
    ex = FakeExecutor()
    asyncio.run(CodexDescriptor().write_credentials(ex, {"auth_json": {"OPENAI_API_KEY": "sk"}}))
    assert json.loads(ex.files[".codex/auth.json"]) == {"OPENAI_API_KEY": "sk"}
    assert ex.modes[".codex/auth.json"] == 0o600


def test_build_spawn_argv_is_fully_autonomous():
    argv = CodexDescriptor().build_spawn_argv("gpt-5.4", "fix it")
    assert argv == ["codex", "exec", "--model", "gpt-5.4",
                    "--dangerously-bypass-approvals-and-sandbox", "fix it"]


def test_extract_result_trims():
    assert CodexDescriptor().extract_result("  done\n") == "done"
```

- [ ] **Step 6: Write `tests/harness/test_cursor.py`**

```python
import asyncio
import json

from vibing_harness import CommandResult
from vibing_harness.descriptors.cursor import CursorDescriptor
from tests.harness.fakes import FakeExecutor


def test_install_runs_curl_bash():
    ex = FakeExecutor()
    asyncio.run(CursorDescriptor().install(ex))
    assert ex.runs[0] == ["bash", "-c", "curl https://cursor.com/install -fsS | bash"]


def test_is_authenticated_false_without_key_file():
    assert asyncio.run(CursorDescriptor().is_authenticated(FakeExecutor())) is False


def test_write_then_authenticated_and_spawn_env():
    ex = FakeExecutor()
    d = CursorDescriptor()
    asyncio.run(d.write_credentials(ex, {"api_key": "key-123"}))
    assert json.loads(ex.files[".config/vibing-harness/cursor.json"]) == {"api_key": "key-123"}
    assert ex.modes[".config/vibing-harness/cursor.json"] == 0o600
    assert asyncio.run(d.is_authenticated(ex)) is True
    assert asyncio.run(d.spawn_env(ex)) == {"CURSOR_API_KEY": "key-123"}


def test_spawn_env_empty_without_key():
    assert asyncio.run(CursorDescriptor().spawn_env(FakeExecutor())) == {}


def test_build_spawn_argv():
    argv = CursorDescriptor().build_spawn_argv("auto", "do it")
    assert argv == ["cursor-agent", "-p", "do it", "--model", "auto",
                    "--force", "--output-format", "text"]


def test_is_installed_checks_version():
    ex = FakeExecutor({"cursor-agent": CommandResult(0, "1.0", "")})
    assert asyncio.run(CursorDescriptor().is_installed(ex)) is True
    assert ex.runs[0] == ["cursor-agent", "--version"]
```

- [ ] **Step 7: Write `tests/harness/test_registry.py`**

```python
from vibing_harness import descriptors


def test_registry_has_codex_and_cursor():
    d = descriptors()
    assert set(d) == {"codex", "cursor"}
    assert d["codex"].name == "codex"
    assert d["cursor"].name == "cursor"
```

- [ ] **Step 8: Run, lint, type-check, commit**

```bash
uv run pytest tests/harness -q
uv run ruff format src/vibing_harness tests/harness
uv run ruff check src tests && uv run mypy src
git add src/vibing_harness tests/harness
git commit -m "feat(harness): port codex + cursor descriptors and registry"
```

---

## Task 3: Control Plane `DevcontainerExecutor`

**Files:**
- Create: `src/vibing_api/core/devcontainer_executor.py`
- Test: `tests/api/test_devcontainer_executor.py`

**Interfaces:**
- Consumes: `vibing_harness.Executor`, `CommandResult`.
- Produces:
  - `DevcontainerExecutor(local_path: str, *, cli: str = "devcontainer", runner: StreamRunner | None = None)`.
  - Implements `Executor`: `run`, `read`, `write`.
  - `async stream(argv: list[str]) -> AsyncIterator[str]` — yields combined stdout/stderr lines from `devcontainer exec` (for install/auth observability).
  - `StreamRunner = Callable[[list[str], bytes | None], AsyncIterator[bytes]]` — injectable seam yielding raw output chunks; the second arg is optional stdin bytes. Default runner uses `asyncio.create_subprocess_exec` with PIPE.
  - `run`/`read` collect the stream to completion; `write` pipes bytes to stdin of `bash -c 'umask <mode>; mkdir -p "$(dirname "$HOME/<path>")"; cat > "$HOME/<path>"'`.

**Notes for implementer:**
- `devcontainer exec --workspace-folder <local_path> <argv...>` runs as the remoteUser.
- The default runner must merge stderr into stdout (`stderr=asyncio.subprocess.STDOUT`) so the stream is the combined log.
- For `write`, compute the umask from `mode` as `0o777 ^ mode` (e.g. `0o600` → umask `077`).
- Path arguments are home-relative; wrap reads/writes in `bash -c` so `$HOME` expands in-container.

- [ ] **Step 1: Write the failing test**

`tests/api/test_devcontainer_executor.py`:

```python
import asyncio
from collections.abc import AsyncIterator

from vibing_api.core.devcontainer_executor import DevcontainerExecutor


def _fake_runner(script: dict[str, bytes]):
    calls: list[tuple[list[str], bytes | None]] = []

    async def runner(argv: list[str], stdin: bytes | None) -> AsyncIterator[bytes]:
        calls.append((argv, stdin))
        # key on the in-container command (everything after `exec --workspace-folder <path>`)
        key = " ".join(argv[3:])
        for k, out in script.items():
            if k in key:
                yield out
                return
        yield b""

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def test_run_collects_combined_output_and_zero_rc():
    runner = _fake_runner({"codex --version": b"codex 1.2.3\n"})
    ex = DevcontainerExecutor("/work", runner=runner)
    result = asyncio.run(ex.run(["codex", "--version"]))
    assert result.returncode == 0
    assert "codex 1.2.3" in result.stdout
    argv = runner.calls[0][0]
    assert argv[:3] == ["devcontainer", "exec", "--workspace-folder"]
    assert argv[3] == "/work"
    assert argv[4:] == ["codex", "--version"]


def test_write_pipes_blob_to_stdin_with_umask_and_home_path():
    runner = _fake_runner({})
    ex = DevcontainerExecutor("/work", runner=runner)
    asyncio.run(ex.write(".codex/auth.json", b'{"k":1}', mode=0o600))
    argv, stdin = runner.calls[0]
    assert stdin == b'{"k":1}'
    shell = argv[-1]
    assert "umask 077" in shell
    assert '$HOME/.codex/auth.json' in shell
    assert "cat >" in shell


def test_read_returns_bytes_and_none_when_absent():
    runner = _fake_runner({'cat "$HOME/.config/vibing-harness/cursor.json"': b'{"api_key":"x"}'})
    ex = DevcontainerExecutor("/work", runner=runner)
    got = asyncio.run(ex.read(".config/vibing-harness/cursor.json"))
    assert got == b'{"api_key":"x"}'


def test_stream_yields_lines():
    runner = _fake_runner({"npm install": b"added 1 package\nok\n"})
    ex = DevcontainerExecutor("/work", runner=runner)

    async def collect():
        return [line async for line in ex.stream(["npm", "install", "-g", "@openai/codex"])]

    lines = asyncio.run(collect())
    assert "added 1 package" in lines[0]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/api/test_devcontainer_executor.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `core/devcontainer_executor.py`**

```python
"""DevcontainerExecutor: the Control Plane's vibing_harness.Executor, backed by
`devcontainer exec` (remoteUser-correct). A PIPE-based runner — distinct from
DevcontainerCliAdapter's temp-file runner, which uses stdin=DEVNULL to dodge the
`devcontainer up` keep-alive pipe-hang — so we can stream install output live and
pipe credentials to stdin. Short-lived `exec` calls stream over pipes safely.

Path args are home-relative; read/write wrap in `bash -c` so $HOME expands in-container."""

import asyncio
from collections.abc import AsyncIterator, Callable

from vibing_harness import CommandResult

StreamRunner = Callable[[list[str], bytes | None], AsyncIterator[bytes]]


async def _default_runner(argv: list[str], stdin: bytes | None) -> AsyncIterator[bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    if stdin is not None and proc.stdin is not None:
        proc.stdin.write(stdin)
        proc.stdin.close()
    async for chunk in proc.stdout:
        yield chunk
    await proc.wait()


class DevcontainerExecutor:
    def __init__(
        self, local_path: str, *, cli: str = "devcontainer", runner: StreamRunner | None = None
    ) -> None:
        self._local_path = local_path
        self._cli = cli
        self._runner = runner or _default_runner

    def _exec(self, argv: list[str]) -> list[str]:
        return [self._cli, "exec", "--workspace-folder", self._local_path, *argv]

    async def _collect(self, argv: list[str], stdin: bytes | None = None) -> bytes:
        out = bytearray()
        async for chunk in self._runner(self._exec(argv), stdin):
            out.extend(chunk)
        return bytes(out)

    async def run(self, argv: list[str]) -> CommandResult:
        # Wrap so a non-zero in-container exit is observable as returncode.
        wrapped = ["bash", "-c", 'exec "$@"', "_"] + argv
        out = await self._collect(wrapped)
        # Re-run via shell that echoes its exit code on the last line.
        return await self._run_with_rc(argv)

    async def _run_with_rc(self, argv: list[str]) -> CommandResult:
        import shlex

        joined = " ".join(shlex.quote(a) for a in argv)
        shell = f"{joined}; printf '\\n__rc=%d__' \"$?\""
        raw = (await self._collect(["bash", "-c", shell])).decode(errors="replace")
        rc = 0
        marker = raw.rfind("__rc=")
        if marker != -1:
            try:
                rc = int(raw[marker + 5 : raw.index("__", marker + 5)])
            except ValueError:
                rc = 0
            raw = raw[:marker].rstrip("\n")
        return CommandResult(returncode=rc, stdout=raw, stderr="")

    async def read(self, path: str) -> bytes | None:
        shell = f'cat "$HOME/{path}"'
        result = await self._run_with_rc(["bash", "-c", shell])
        if result.returncode != 0:
            return None
        return result.stdout.encode()

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        umask = 0o777 ^ mode
        shell = (
            f'umask {umask:03o}; mkdir -p "$(dirname "$HOME/{path}")"; cat > "$HOME/{path}"'
        )
        await self._collect(["bash", "-c", shell], stdin=data)

    async def stream(self, argv: list[str]) -> AsyncIterator[str]:
        buffer = ""
        async for chunk in self._runner(self._exec(argv), None):
            buffer += chunk.decode(errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                yield line
        if buffer:
            yield buffer
```

> Implementer note: simplify `run` to call `_run_with_rc` directly — the first `_collect` in the draft above is redundant; delete it so `run` is just `return await self._run_with_rc(argv)`. Keep tests green.

- [ ] **Step 4: Reconcile the test's argv expectation**

The `__rc__` shell wrapping means `run`'s argv is `["bash", "-c", "<shell>"]`, not the bare `["codex","--version"]`. Update `test_run_collects_combined_output_and_zero_rc` to assert on the *shell string* instead:

```python
def test_run_collects_combined_output_and_zero_rc():
    runner = _fake_runner({"codex --version": b"codex 1.2.3\n__rc=0__"})
    ex = DevcontainerExecutor("/work", runner=runner)
    result = asyncio.run(ex.run(["codex", "--version"]))
    assert result.returncode == 0
    assert "codex 1.2.3" in result.stdout
    argv = runner.calls[0][0]
    assert argv[:4] == ["devcontainer", "exec", "--workspace-folder", "/work"]
    assert "codex --version" in argv[-1]
```

And `_fake_runner`'s `key` should match the shell string: change `key = " ".join(argv[3:])` to `key = " ".join(argv[4:])` (everything after the workspace path).

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/api/test_devcontainer_executor.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff format src/vibing_api/core/devcontainer_executor.py tests/api/test_devcontainer_executor.py
uv run ruff check src tests && uv run mypy src
git add src/vibing_api/core/devcontainer_executor.py tests/api/test_devcontainer_executor.py
git commit -m "feat(api): DevcontainerExecutor — vibing_harness.Executor over devcontainer exec"
```

---

## Task 4: Control Plane `harness_service`

**Files:**
- Create: `src/vibing_api/core/harness_service.py`
- Test: `tests/api/test_harness_service.py`

**Interfaces:**
- Consumes: `vibing_harness` (`descriptors`, `Executor`, `HarnessStatus`), `LiveStateStore`, `Broadcaster`/`SseEvent`.
- Produces:
  - `async compute_status(ex: Executor) -> list[HarnessStatus]` — runs all descriptors' `status` concurrently.
  - `async refresh(live, devcontainer_id, ex, broadcaster=None) -> list[HarnessStatus]` — compute, `live.set_harness(...)`, publish `harnesses` SSE.
  - `async install_stream(ex, name) -> AsyncIterator[str]` — install-if-missing, yielding `ex.stream(...)` lines (uses the descriptor's install command via `ex.stream`).
  - `async authenticate_stream(ex, name, blob) -> AsyncIterator[str]` — install-if-missing (streamed) then `write_credentials`.
- `live.set_harness` now stores `vibing_harness.HarnessStatus` (see Task 7 for the LiveStateStore type change). For this task, convert to the API schema at the route layer.

**Notes:** `install_stream`/`authenticate_stream` need the descriptor's install argv. Add to `HarnessDescriptor` a tiny accessor used only for streaming: keep it simple — `harness_service` calls `ex.stream(<argv>)` where argv comes from a new `install_argv()` method. To avoid widening the descriptor contract, instead expose install streaming by having the executor stream while the descriptor drives: simplest is `harness_service` checking `await descriptor.is_installed(ex)` then `async for line in ex.stream(descriptor_install_argv)`. Add `install_argv(self) -> list[str]` to each descriptor (codex: `["npm","install","-g","@openai/codex"]`; cursor: `["bash","-c", _INSTALL]`) and have `install()` delegate to it. Update Task 2 descriptors accordingly when implementing — see Step 1.

- [ ] **Step 1: Add `install_argv()` to descriptors and base**

In `src/vibing_harness/base.py`, add an abstract method:

```python
    @abstractmethod
    def install_argv(self) -> list[str]: ...
```

In `descriptors/codex.py`:

```python
    def install_argv(self) -> list[str]:
        return ["npm", "install", "-g", "@openai/codex"]

    async def install(self, ex: Executor) -> None:
        await ex.run(self.install_argv())
```

In `descriptors/cursor.py`:

```python
    def install_argv(self) -> list[str]:
        return ["bash", "-c", _INSTALL]

    async def install(self, ex: Executor) -> None:
        await ex.run(self.install_argv())
```

Update `tests/harness/test_base.py` `_Stub` to add `def install_argv(self): return []`.

- [ ] **Step 2: Write the failing service test**

`tests/api/test_harness_service.py`:

```python
import asyncio

from vibing_api.core import harness_service
from vibing_api.core.live_state import LiveStateStore
from tests.harness.fakes import FakeExecutor
from vibing_harness import CommandResult


def test_compute_status_runs_all_descriptors():
    ex = FakeExecutor({
        "codex": CommandResult(0, "", ""),
        "cursor-agent": CommandResult(127, "", ""),
    })
    statuses = asyncio.run(harness_service.compute_status(ex))
    by = {s.name: s for s in statuses}
    assert by["codex"].installed is True
    assert by["cursor"].installed is False


def test_refresh_caches_and_returns():
    ex = FakeExecutor({"codex": CommandResult(0, "", ""), "cursor-agent": CommandResult(0, "", "")})
    live = LiveStateStore()
    statuses = asyncio.run(harness_service.refresh(live, "dc1", ex))
    assert live.get_harness("dc1") == statuses


def test_authenticate_writes_credentials():
    ex = FakeExecutor({"codex": CommandResult(0, "", "")})

    async def go():
        return [line async for line in
                harness_service.authenticate_stream(ex, "codex", {"auth_json": {"K": "v"}})]

    asyncio.run(go())
    assert ".codex/auth.json" in ex.files
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/api/test_harness_service.py -q`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement `core/harness_service.py`**

```python
"""Harness setup, Control-Plane-owned (ADR-0019). Drives vibing_harness descriptors
through an injected Executor (DevcontainerExecutor in production). Status is computed
and cached in LiveStateStore; install/auth stream their output for live observability."""

import asyncio
from collections.abc import AsyncIterator

from vibing_harness import Executor, HarnessStatus, descriptors

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.live_state import LiveStateStore


async def compute_status(ex: Executor) -> list[HarnessStatus]:
    items = descriptors().values()
    return list(await asyncio.gather(*(d.status(ex) for d in items)))


async def refresh(
    live: LiveStateStore,
    devcontainer_id: str,
    ex: Executor,
    broadcaster: Broadcaster | None = None,
) -> list[HarnessStatus]:
    statuses = await compute_status(ex)
    live.set_harness(devcontainer_id, statuses)
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="harnesses", ids=[devcontainer_id]))
    return statuses


async def install_stream(ex, name: str) -> AsyncIterator[str]:
    d = descriptors()[name]
    if await d.is_installed(ex):
        yield f"{name} already installed"
        return
    async for line in ex.stream(d.install_argv()):
        yield line


async def authenticate_stream(ex, name: str, blob: dict) -> AsyncIterator[str]:
    d = descriptors()[name]
    if not await d.is_installed(ex):
        async for line in ex.stream(d.install_argv()):
            yield line
    await d.write_credentials(ex, blob)
    yield f"{name} authenticated"
```

> `install_stream`/`authenticate_stream` take `ex` untyped to allow `DevcontainerExecutor` (which has `.stream`); the `Executor` Protocol intentionally omits `stream`. Type the param as `DevcontainerExecutor` to keep mypy honest, importing it lazily inside `core` to avoid a cycle, or annotate as `"DevcontainerExecutor"`.

- [ ] **Step 5: Type `ex` correctly**

Add at top of `harness_service.py`:

```python
from vibing_api.core.devcontainer_executor import DevcontainerExecutor
```

and annotate the stream functions' `ex: DevcontainerExecutor`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/api/test_harness_service.py tests/harness -q`
Expected: PASS.

> Note: `live.set_harness` currently takes `list[HarnessStatusItem]` (protocol). This task passes `vibing_harness.HarnessStatus`. Task 7 changes `LiveStateStore` to store `HarnessStatus`. **Until Task 7**, temporarily keep the test green by having `refresh` not depend on the stored type (the equality test compares what we stored to what we returned — same objects — so it passes regardless). Do not import `HarnessStatusItem` here.

- [ ] **Step 7: Lint, type-check, commit**

```bash
uv run ruff format src/vibing_harness src/vibing_api/core/harness_service.py tests/api/test_harness_service.py
uv run ruff check src tests && uv run mypy src
git add src/vibing_harness tests/harness src/vibing_api/core/harness_service.py tests/api/test_harness_service.py
git commit -m "feat(api): harness_service — CP-owned install/auth/status via descriptors"
```

---

## Task 5: Control Plane routes — streaming install/auth + refresh + cached GET

**Files:**
- Modify: `src/vibing_api/api/routes/harnesses.py` (full rewrite)
- Modify: `src/vibing_api/api/schemas/harnesses.py` (build list from `HarnessStatus`)
- Test: `tests/api/test_harnesses_api.py`, `tests/api/test_harness_install_api.py` (rewrite)

**Interfaces:**
- Consumes: `harness_service`, `DevcontainerExecutor`, `LiveStateStore`, `DevcontainerCatalog` (to resolve `devcontainer_id → local_path`), `HarnessCredentialRepository`.
- Produces HTTP:
  - `GET /devcontainers/{id}/harnesses` → `HarnessStatusList` from cache (`known=False` if absent).
  - `POST /devcontainers/{id}/harnesses/{name}/install` → `text/plain` streaming (chunked) install log; on completion refresh + SSE.
  - `POST /devcontainers/{id}/harnesses/{name}/authenticate` → `text/plain` streaming; on completion refresh + SSE.
  - `POST /devcontainers/{id}/harnesses/refresh` → `HarnessStatusList` (recompute + cache + SSE).

**Notes:**
- Resolve `local_path` from the catalog the same way other lifecycle routes do (look at `devcontainers.py` for the catalog accessor on `request.app.state`).
- Build `DevcontainerExecutor(local_path)`.
- Use `fastapi.responses.StreamingResponse(generator, media_type="text/plain")`. After the install/auth generator exhausts, call `await harness_service.refresh(live, id, ex, broadcaster)` — do this *inside* the generator's `finally` so it runs after streaming completes.
- The install/auth endpoints no longer require a connected runtime — remove the `RuntimeUnavailableError` guard. They require the **container running**; if `DevcontainerExecutor` calls fail, the stream surfaces the error text.

- [ ] **Step 1: Rewrite `api/schemas/harnesses.py` helper**

Add a constructor from domain status:

```python
from pydantic import BaseModel

from vibing_harness import HarnessStatus


class HarnessStatusItem(BaseModel):
    name: str
    installed: bool
    authenticated: bool

    @classmethod
    def from_status(cls, s: HarnessStatus) -> "HarnessStatusItem":
        return cls(name=s.name, installed=s.installed, authenticated=s.authenticated)


class HarnessStatusList(BaseModel):
    items: list[HarnessStatusItem]
    known: bool = False
```

- [ ] **Step 2: Write the failing route tests**

Rewrite `tests/api/test_harnesses_api.py` (use the existing app fixture/test client pattern from the file's current top — reuse imports). Key cases:

```python
def test_get_harnesses_unknown_when_no_cache(client):
    resp = client.get("/api/v1/devcontainers/dc-x/harnesses")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "known": False}


def test_refresh_recomputes_and_caches(client, app, monkeypatch):
    # monkeypatch harness_service.compute_status to avoid real devcontainer exec
    import vibing_api.core.harness_service as hs
    from vibing_harness import HarnessStatus

    async def fake_compute(ex):
        return [HarnessStatus("codex", True, True), HarnessStatus("cursor", False, False)]

    monkeypatch.setattr(hs, "compute_status", fake_compute)
    # ensure the devcontainer id resolves to a local_path in the catalog fixture
    resp = client.post(f"/api/v1/devcontainers/{KNOWN_ID}/harnesses/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["known"] is True
    assert {i["name"]: i["installed"] for i in body["items"]} == {"codex": True, "cursor": False}


def test_install_streams_text(client, app, monkeypatch):
    import vibing_api.core.harness_service as hs

    async def fake_install_stream(ex, name):
        yield "installing"
        yield "done"

    async def fake_refresh(live, id, ex, broadcaster=None):
        return []

    monkeypatch.setattr(hs, "install_stream", fake_install_stream)
    monkeypatch.setattr(hs, "refresh", fake_refresh)
    resp = client.post(f"/api/v1/devcontainers/{KNOWN_ID}/harnesses/codex/install")
    assert resp.status_code == 200
    assert "installing" in resp.text and "done" in resp.text
```

> Implementer: `KNOWN_ID` must be a devcontainer present in the catalog with a `local_path`. Follow the existing fixture in `tests/api/conftest.py` (inspect it) — insert a manual devcontainer row or reuse an existing fixture id. If the catalog needs a real dir, use `tmp_path`.

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/api/test_harnesses_api.py -q`
Expected: FAIL.

- [ ] **Step 4: Rewrite `api/routes/harnesses.py`**

```python
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from vibing_api.api.schemas.harnesses import HarnessStatusItem, HarnessStatusList
from vibing_api.core import harness_service
from vibing_api.core.database import get_connection
from vibing_api.core.devcontainer_executor import DevcontainerExecutor
from vibing_api.core.live_state import LiveStateStore
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository

router = APIRouter(tags=["harnesses"], prefix="/devcontainers")


def _executor(request: Request, devcontainer_id: str) -> DevcontainerExecutor:
    catalog = request.app.state.catalog
    record = catalog.get(devcontainer_id)  # follow catalog's real accessor name
    return DevcontainerExecutor(record.local_path)


@router.get("/{devcontainer_id}/harnesses", response_model=HarnessStatusList)
def list_harnesses(devcontainer_id: str, request: Request) -> HarnessStatusList:
    live: LiveStateStore = request.app.state.live_state
    cached = live.get_harness(devcontainer_id)
    if cached is None:
        return HarnessStatusList(items=[], known=False)
    return HarnessStatusList(
        items=[HarnessStatusItem.from_status(s) for s in cached], known=True
    )


@router.post("/{devcontainer_id}/harnesses/refresh", response_model=HarnessStatusList)
async def refresh_harnesses(devcontainer_id: str, request: Request) -> HarnessStatusList:
    live: LiveStateStore = request.app.state.live_state
    broadcaster = getattr(request.app.state, "broadcaster", None)
    ex = _executor(request, devcontainer_id)
    statuses = await harness_service.refresh(live, devcontainer_id, ex, broadcaster)
    return HarnessStatusList(
        items=[HarnessStatusItem.from_status(s) for s in statuses], known=True
    )


def _stream_then_refresh(request: Request, devcontainer_id: str, gen) -> StreamingResponse:
    live: LiveStateStore = request.app.state.live_state
    broadcaster = getattr(request.app.state, "broadcaster", None)
    ex = _executor(request, devcontainer_id)

    async def body() -> AsyncIterator[str]:
        try:
            async for line in gen(ex):
                yield line + "\n"
        finally:
            await harness_service.refresh(live, devcontainer_id, ex, broadcaster)

    return StreamingResponse(body(), media_type="text/plain")


@router.post("/{devcontainer_id}/harnesses/{name}/install", status_code=status.HTTP_200_OK)
def install_harness(devcontainer_id: str, name: str, request: Request) -> StreamingResponse:
    return _stream_then_refresh(
        request, devcontainer_id, lambda ex: harness_service.install_stream(ex, name)
    )


@router.post("/{devcontainer_id}/harnesses/{name}/authenticate", status_code=status.HTTP_200_OK)
def authenticate_harness(devcontainer_id: str, name: str, request: Request) -> StreamingResponse:
    with get_connection() as conn:
        blob = HarnessCredentialRepository(conn).get(name) or {}
    return _stream_then_refresh(
        request, devcontainer_id, lambda ex: harness_service.authenticate_stream(ex, name, blob)
    )
```

> Implementer: confirm the catalog accessor (`request.app.state.catalog` / method name) against `devcontainers.py`; reuse exactly what lifecycle routes use to resolve `local_path`. If credential capture endpoints existed in the old `harnesses.py`, preserve them (check git diff before deleting).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/api/test_harnesses_api.py tests/api/test_harness_install_api.py -q`
Expected: PASS. Fix fixtures as needed.

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff format src/vibing_api/api/routes/harnesses.py src/vibing_api/api/schemas/harnesses.py tests/api/test_harnesses_api.py tests/api/test_harness_install_api.py
uv run ruff check src tests && uv run mypy src
git add src/vibing_api/api/routes/harnesses.py src/vibing_api/api/schemas/harnesses.py tests/api
git commit -m "feat(api): streaming install/auth + refresh + cached GET harnesses"
```

---

## Task 6: Runtime — LocalExecutor + rewire to vibing_harness, delete adapters

**Files:**
- Create: `src/vibing_devcontainer_runtime/local_executor.py`
- Modify: `src/vibing_devcontainer_runtime/mcp_server.py`
- Modify: `src/vibing_devcontainer_runtime/delegated_runs.py`
- Modify: `src/vibing_devcontainer_runtime/cli.py`
- Modify: `src/vibing_devcontainer_runtime/runtime_client.py`
- Delete: `src/vibing_devcontainer_runtime/harness/` (whole dir), `harness_manager.py`, `command_handler.py`
- Delete tests: `tests/devcontainer_runtime/test_codex_adapter.py`, `test_cursor_adapter.py`, `test_harness_base.py`, `test_harness_manager.py`, `test_harness_registry.py`, `test_command_handler_harness.py`, `test_harness_process.py`
- Create test: `tests/devcontainer_runtime/test_local_executor.py`
- Modify tests: `test_delegated_runs.py`, `test_mcp_server.py`, `test_runtime_client.py`, `test_cli.py`

**Interfaces:**
- Produces:
  - `LocalExecutor(home: Path | None = None)` implementing `vibing_harness.Executor` via `asyncio.create_subprocess_exec` + local file IO (paths home-relative, joined to `home`).
  - `build_mcp_server(executor, descriptors_map, delegated_runs, *, host, port)` — `list_harnesses` calls `descriptor.status(executor)`.
  - `DelegatedRunManager(descriptors_map, executor, *, devcontainer_id, workspace, max_concurrent=4, report=None)` — `spawn` uses `descriptor.build_spawn_argv` + `await descriptor.spawn_env(executor)`; auth check via `descriptor.is_authenticated(executor)`. The subprocess still runs through a process factory for terminate support.

**Notes:** `delegated_runs.py` keeps its `HarnessProcessFactory` for spawn (needs `terminate`), but harness *knowledge* now comes from `vibing_harness` descriptors + a `LocalExecutor`. Move `process.py` to remain (rename import path if convenient) — it is the spawn-process seam, not harness knowledge. Keep `harness/process.py`? It lives under `harness/`, which we delete. **Move `process.py` to `src/vibing_devcontainer_runtime/process.py`** (top level) and update imports.

- [ ] **Step 1: Move the process seam out of `harness/`**

```bash
git mv src/vibing_devcontainer_runtime/harness/process.py src/vibing_devcontainer_runtime/process.py
```

- [ ] **Step 2: Write `local_executor.py` + test (TDD)**

`tests/devcontainer_runtime/test_local_executor.py`:

```python
import asyncio

from vibing_devcontainer_runtime.local_executor import LocalExecutor


def test_run_executes_real_command(tmp_path):
    ex = LocalExecutor(home=tmp_path)
    result = asyncio.run(ex.run(["bash", "-c", "echo hi"]))
    assert result.returncode == 0
    assert "hi" in result.stdout


def test_run_missing_binary_returns_127(tmp_path):
    ex = LocalExecutor(home=tmp_path)
    result = asyncio.run(ex.run(["definitely-not-a-binary-xyz"]))
    assert result.returncode == 127


def test_write_then_read_round_trip_home_relative(tmp_path):
    ex = LocalExecutor(home=tmp_path)
    asyncio.run(ex.write(".config/x/cred.json", b"secret", mode=0o600))
    path = tmp_path / ".config" / "x" / "cred.json"
    assert path.read_bytes() == b"secret"
    assert (path.stat().st_mode & 0o777) == 0o600
    assert asyncio.run(ex.read(".config/x/cred.json")) == b"secret"


def test_read_absent_returns_none(tmp_path):
    assert asyncio.run(LocalExecutor(home=tmp_path).read("nope")) is None
```

`src/vibing_devcontainer_runtime/local_executor.py`:

```python
"""LocalExecutor: vibing_harness.Executor for the in-container runtime — local
subprocess + direct file IO. Home-relative paths join the runtime's $HOME."""

import asyncio
from pathlib import Path

from vibing_harness import CommandResult


class LocalExecutor:
    def __init__(self, home: Path | None = None) -> None:
        self._home = home or Path.home()

    async def run(self, argv: list[str]) -> CommandResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except FileNotFoundError:
            return CommandResult(127, "", "binary not found")
        out, err = await proc.communicate()
        return CommandResult(proc.returncode or 0, out.decode(errors="replace"),
                             err.decode(errors="replace"))

    async def read(self, path: str) -> bytes | None:
        target = self._home / path
        if not target.exists():
            return None
        return target.read_bytes()

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        target = self._home / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(mode)
```

Run: `uv run pytest tests/devcontainer_runtime/test_local_executor.py -q` → PASS.

- [ ] **Step 3: Rewrite `delegated_runs.py` to use descriptors + executor**

Change the constructor and `spawn`/`_await_run` to take `descriptors: dict[str, HarnessDescriptor]` and `executor: Executor` instead of `adapters`. Replace:
- `adapter = self._adapters[harness]` → `descriptor = self._descriptors[harness]`
- `await adapter.is_authenticated()` → `await descriptor.is_authenticated(self._executor)`
- `adapter.build_spawn_argv(model, prompt)` → unchanged signature
- `adapter.spawn_env()` → `await descriptor.spawn_env(self._executor)`
- `adapter.extract_result(...)` → `descriptor.extract_result(...)`

Keep `self._factory` (process factory) for building the spawn process. Update `test_delegated_runs.py` to construct with a `descriptors` map (use `vibing_harness.descriptors()` or a stub) and a `FakeExecutor`-like object plus the existing fake process factory.

- [ ] **Step 4: Rewrite `mcp_server.py`**

```python
from typing import Any

from mcp.server.fastmcp import FastMCP
from vibing_harness import Executor, HarnessDescriptor

from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager


def build_mcp_server(
    executor: Executor,
    descriptors_map: dict[str, HarnessDescriptor],
    delegated_runs: DelegatedRunManager,
    *,
    host: str = "127.0.0.1",
    port: int = 8848,
) -> FastMCP:
    mcp = FastMCP("vibing-harness", host=host, port=port, stateless_http=True, json_response=True)

    @mcp.tool()
    async def list_harnesses() -> list[dict[str, Any]]:
        """List managed coding harnesses with installed/authenticated status."""
        out = []
        for d in descriptors_map.values():
            s = await d.status(executor)
            out.append({"name": s.name, "installed": s.installed, "authenticated": s.authenticated})
        return out

    @mcp.tool()
    async def spawn(harness: str, model: str, prompt: str, detached: bool = False,
                    cwd: str | None = None) -> dict[str, Any]:
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

Update `test_mcp_server.py` to pass `(executor, descriptors_map, delegated_runs)`.

- [ ] **Step 5: Rewrite `runtime_client.py` to outbound-only**

Remove command handling: delete `CommandHandler`, `_dispatch`, the command queue/consumer, and the `handler` constructor arg. Keep: connect/reconnect loop, `register` send, `on_registered` hook, `send_envelope`. The `_run_session` becomes: send register → call `on_registered` → keep the socket open, draining/ignoring inbound frames until disconnect (still need to `await ws.recv()` in a loop to detect disconnects, but discard messages). Remove imports of `Command`, `CommandEnvelope`.

```python
    async def _run_session(self, ws: Any) -> None:
        self._ws = ws
        try:
            await ws.send(encode(self._register))
            logger.info("Registered with control plane")
            if self._on_registered is not None:
                await self._on_registered()
            while not self._stopped:
                await ws.recv()  # drain; channel is outbound-only
        finally:
            self._ws = None
```

Update `test_runtime_client.py`: remove command-dispatch tests; keep connect/register/reconnect/send_envelope tests.

- [ ] **Step 6: Rewrite `cli.py`**

```python
import asyncio
from pathlib import Path

import typer
from logzero import logger
from mcp.server.fastmcp import FastMCP
from vibing_harness import descriptors as harness_descriptors
from vibing_protocol import DelegatedRunItem, DelegatedRunsEnvelope, RegisterEnvelope

from vibing_devcontainer_runtime.delegated_runs import DelegatedRunManager
from vibing_devcontainer_runtime.local_executor import LocalExecutor
from vibing_devcontainer_runtime.mcp_server import build_mcp_server
from vibing_devcontainer_runtime.process import real_process_factory
from vibing_devcontainer_runtime.runtime_client import RuntimeChannelClient

DEFAULT_CONTROL_PLANE_URL = "ws://host.docker.internal:8080/api/v1/runtime/agent/ws"

cli = typer.Typer(add_completion=False, help="Devcontainer Runtime: MCP delegation server.")


async def _serve_async(control_plane_url, devcontainer_id, mcp_host, mcp_port, workspace) -> None:
    executor = LocalExecutor(Path.home())
    descriptors_map = harness_descriptors()

    delegated_runs = DelegatedRunManager(
        descriptors_map, executor, real_process_factory,
        devcontainer_id=devcontainer_id, workspace=workspace,
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
        await _report_runs()

    register = RegisterEnvelope(devcontainer_id=devcontainer_id)
    client = RuntimeChannelClient(control_plane_url, register, on_registered=_on_registered)
    delegated_runs.report = _report_runs

    mcp: FastMCP = build_mcp_server(
        executor, descriptors_map, delegated_runs, host=mcp_host, port=mcp_port
    )
    await asyncio.gather(client.run(), mcp.run_streamable_http_async())
```

(Keep `_serve_blocking`, `serve` callback, `main` unchanged except the dropped args.) Note `RuntimeChannelClient.__init__` loses its `handler` param — update signature accordingly. `DelegatedRunManager` positional order: `(descriptors_map, executor, factory, ...)` — match Step 3.

- [ ] **Step 7: Delete the dead harness code**

```bash
git rm -r src/vibing_devcontainer_runtime/harness
git rm src/vibing_devcontainer_runtime/harness_manager.py src/vibing_devcontainer_runtime/command_handler.py
git rm tests/devcontainer_runtime/test_codex_adapter.py tests/devcontainer_runtime/test_cursor_adapter.py \
       tests/devcontainer_runtime/test_harness_base.py tests/devcontainer_runtime/test_harness_manager.py \
       tests/devcontainer_runtime/test_harness_registry.py tests/devcontainer_runtime/test_command_handler_harness.py
git mv tests/devcontainer_runtime/test_harness_process.py tests/devcontainer_runtime/test_process.py
```

Update `test_process.py` imports: `from vibing_devcontainer_runtime.process import ...`.

- [ ] **Step 8: Run the runtime suite**

Run: `uv run pytest tests/devcontainer_runtime -q`
Expected: PASS (after test updates). Fix import errors iteratively.

- [ ] **Step 9: Lint, type-check, commit**

```bash
uv run ruff format src/vibing_devcontainer_runtime tests/devcontainer_runtime
uv run ruff check src tests && uv run mypy src
git add -A src/vibing_devcontainer_runtime tests/devcontainer_runtime
git commit -m "refactor(runtime): delegation-only — use vibing_harness, delete harness adapters + commands"
```

---

## Task 7: Protocol cleanup + CP intake/channel trims

**Files:**
- Delete: `src/vibing_protocol/commands.py`
- Modify: `src/vibing_protocol/messages.py` (drop `CommandEnvelope`, `HarnessStatusEnvelope`, `HarnessStatusItem`)
- Modify: `src/vibing_protocol/__init__.py`, `src/vibing_protocol/channel.py` (if it references removed types)
- Modify: `src/vibing_api/core/runtime_channel.py` (drop Command send)
- Modify: `src/vibing_api/api/routes/runtime.py` (drop harness_status handling)
- Modify: `src/vibing_api/core/runtime_intake.py` (drop `record_harness_status`)
- Modify: `src/vibing_api/core/live_state.py` (store `vibing_harness.HarnessStatus`; drop `evict_harness` call on disconnect)
- Modify tests: `tests/protocol/*`, `tests/api/test_runtime_*`, any referencing removed types.

**Interfaces:**
- `vibing_protocol` public surface after: `RegisterEnvelope`, `DelegatedRunsEnvelope`, `DelegatedRunItem`, `encode`, `decode`.
- `LiveStateStore.set_harness(id, list[HarnessStatus])` / `get_harness(id) -> list[HarnessStatus] | None` now typed on `vibing_harness.HarnessStatus`.
- `RuntimeRegistry` loses `send_command`; keeps `is_connected`/`register`/`unregister`.

- [ ] **Step 1: Delete `commands.py`, trim `messages.py`**

`git rm src/vibing_protocol/commands.py`. In `messages.py` remove the `from .commands import Command` import and the `CommandEnvelope`, `HarnessStatusItem`, `HarnessStatusEnvelope` classes. Keep `RegisterEnvelope`, `DelegatedRunItem`, `DelegatedRunsEnvelope`.

- [ ] **Step 2: Update `vibing_protocol/__init__.py`**

Remove exports of `Command`, `CommandType`, `CommandEnvelope`, `HarnessStatusEnvelope`, `HarnessStatusItem`, `COMMAND_TYPES`. Keep `RegisterEnvelope`, `DelegatedRunItem`, `DelegatedRunsEnvelope`, `encode`, `decode`.

- [ ] **Step 3: Update `vibing_protocol/CLAUDE.md`** — already reflects target (done in design phase). Verify it matches.

- [ ] **Step 4: Trim `runtime_channel.py`**

```python
"""Per-devcontainer runtime connection registry (liveness/intake only; outbound-only channel)."""

from typing import Protocol

from fastapi import WebSocket


class RuntimeConnection(Protocol):
    """A live link to one Devcontainer Runtime."""


class WebSocketRuntimeConnection:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket


class RuntimeRegistry:
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
```

- [ ] **Step 5: Trim `runtime.py` route**

Remove the `harness_status` branch and the `HarnessStatusEnvelope` import; in `unregister()` remove `live_state.evict_harness(devcontainer_id)` (status is now container-scoped, not runtime-scoped). Remove `record_harness_status` import. Keep `delegated_runs` handling + register/clear-transient.

- [ ] **Step 6: Trim `runtime_intake.py`**

Delete `record_harness_status` and its `HarnessStatusItem` import. Keep `persist_delegated_runs`.

- [ ] **Step 7: Update `live_state.py`**

Change the harness map type to `vibing_harness.HarnessStatus`:

```python
from vibing_harness import HarnessStatus
...
        self._harness: dict[str, list[HarnessStatus]] = {}
...
    def set_harness(self, devcontainer_id: str, items: list[HarnessStatus]) -> None:
        self._harness[devcontainer_id] = items

    def get_harness(self, devcontainer_id: str) -> list[HarnessStatus] | None:
        return self._harness.get(devcontainer_id)
```

Keep `evict_harness` method (may still be useful on container stop) but it is no longer called from runtime disconnect. Update the module docstring's "(evicted on disconnect → unknown)" line to "(container-scoped; cleared on container stop)".

- [ ] **Step 8: Fix fallout + run full suite**

Search for now-dead imports: `grep -rn "HarnessStatusEnvelope\|CommandEnvelope\|CommandType\|record_harness_status\|send_command" src tests`. Fix each. Update `tests/protocol` and `tests/api/test_runtime_*` accordingly.

Run: `uv run pytest -q`
Expected: PASS (full suite).

- [ ] **Step 9: Lint, type-check, commit**

```bash
uv run ruff format src tests
uv run ruff check src tests && uv run mypy src
git add -A
git commit -m "refactor(protocol): remove Command + HarnessStatus envelopes; channel is outbound-only"
```

---

## Task 8: Frontend — streaming install/auth, refresh button, container-scoped status

**Files:**
- Modify: `apps/web/src/lib/api/endpoints.ts`
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/components/HarnessList.tsx`
- Modify: `apps/web/src/mock/handlers.ts` (+ harness mock handlers) and related tests
- Test: `apps/web/src/components/__tests__/HarnessList.test.tsx`

**Interfaces:**
- `installHarness`/`authenticateHarness` now consume a streamed `text/plain` response (return the final text or stream lines to a callback). Simplest: return `Promise<void>` that resolves when the stream ends; the component refetches status via `onChange` (SSE invalidation also fires).
- Add `refreshHarnesses(devcontainerId): Promise<HarnessStatusList>` → `POST /harnesses/refresh`.
- Add a refresh control to `HarnessList` calling `refreshHarnesses` then `onChange`.

- [ ] **Step 1: Update `endpoints.ts`**

```ts
export const installHarness = (devcontainerId: string, name: string): Promise<void> =>
  streamText(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/${encodeURIComponent(name)}/install`)

export const authenticateHarness = (devcontainerId: string, name: string): Promise<void> =>
  streamText(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/${encodeURIComponent(name)}/authenticate`)

export const refreshHarnesses = (devcontainerId: string): Promise<HarnessStatusList> =>
  sendJson<HarnessStatusList>(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/refresh`, 'POST')
```

Add a `streamText(path)` helper in `client.ts` that `POST`s and drains the body (`response.body` reader) to completion, optionally invoking an `onLine` callback. For the first cut, drain and resolve.

- [ ] **Step 2: Add refresh button + stream-aware busy state to `HarnessList.tsx`**

Add a header refresh button calling `refreshHarnesses(devcontainerId).then(onChange)`. Keep the install/login icon buttons; their `run()` already awaits the promise and calls `onChange`. Optionally show streamed lines in a tooltip/expander (defer — busy spinner is enough for v1).

- [ ] **Step 3: Update mock handlers**

In `apps/web/src/mock/handlers.ts`, change the install/auth handlers to return a streamed text body (MSW supports `new Response(stream)` or a simple text body), and add a `POST /harnesses/refresh` handler returning a `HarnessStatusList`. Update `harnessHandlers` fixtures so `known` reflects container-running.

- [ ] **Step 4: Update component tests**

Adjust `HarnessList.test.tsx` for the refresh button and the void-returning install/auth. Run:

```bash
cd apps/web && pnpm test -- HarnessList
```
Expected: PASS.

- [ ] **Step 5: Lint + full web checks + commit**

```bash
cd apps/web && pnpm lint && pnpm test
cd /workspaces/vibing
git add apps/web
git commit -m "feat(web): streaming install/auth, harness refresh, container-scoped status"
```

---

## Task 9: Final verification + docs coherence

**Files:** docs already updated in design phase (`ADR-0019`, `CONTEXT.md`, all `CLAUDE.md`). This task verifies nothing drifted.

- [ ] **Step 1: Full backend gate**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest -q
```
Expected: all PASS.

- [ ] **Step 2: Grep for stragglers**

```bash
grep -rn "authenticate_harness\|install_harness\|harness_manager\|HarnessAdapter\|HarnessStatusEnvelope\|record_harness_status" src tests
```
Expected: no hits in code (only ADR/docs prose). Fix any code hits.

- [ ] **Step 3: Build**

```bash
uv build
```
Expected: wheel builds, includes `vibing_harness`.

- [ ] **Step 4: Confirm CLAUDE.md/CONTEXT coherence**

Re-read `src/CLAUDE.md`, `src/vibing_api/CLAUDE.md`, `src/vibing_devcontainer_runtime/CLAUDE.md`, `src/vibing_protocol/CLAUDE.md`, `CONTEXT.md` against the final code. They were written to the target; verify file/function names match what was built (e.g. `harness_service.py`, `devcontainer_executor.py`, `local_executor.py`). Fix drift.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: verify CP-owned harness setup — full gate green"
```

---

## Self-Review Notes

- **Spec coverage:** package (T1–T2), CP executor (T3), CP service (T4), CP routes incl. refresh button backing (T5), runtime shrink + deletions (T6), protocol/channel/intake/live_state trims (T7), frontend incl. manual refresh (T8), verification + docs (T9). All ADR-0019 points covered: `devcontainer exec` install/auth/status, streaming observability, container-scoped cached status, manual refresh, Command-direction deletion, `vibing_harness` executor-injected package.
- **Sequencing keeps green:** additive first (T1–T5 leave protocol intact), runtime rewrite (T6) stops *sending* harness_status before T7 *removes* the type, T7 deletes the now-unused protocol surface and CP intake together.
- **Known sharp edges flagged inline:** catalog accessor name in T5 (verify against `devcontainers.py`); `DevcontainerExecutor.run` rc-capture via shell marker (T3 Step 4 reconciles the test); `harness_service` stream typing vs `Executor` Protocol (T4 Step 5); `live.set_harness` type migration deferred to T7 (T4 Step 6 note).
- **Credential-capture endpoints:** T5 Step 4 note — preserve any existing capture route from the old `harnesses.py` (check the git diff before overwriting).
