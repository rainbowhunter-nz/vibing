# Vibing CLI: runtime group + HTTP-client commands — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regroup the two runtime workers under a `vibing runtime` group and add `httpx`-based client commands that drive every API endpoint from the terminal.

**Architecture:** A new `src/vibing_cli/client/` subpackage holds thin Typer apps (one per API resource) that call the running API via a shared `http.request()` helper, rendering responses with rich (`render()`) or raw JSON (`--json`). The root `vibing_cli/__init__.py` mounts a `runtime` group plus the four client groups. Base URL comes from env (`VIBING_API_URL` + `VIBING_API_V1_PREFIX`).

**Tech Stack:** Python, Typer, Rich, httpx (all already dependencies), pytest + Typer `CliRunner` + `httpx.MockTransport`.

Spec: `docs/superpowers/specs/2026-06-02-vibing-cli-runtime-group-and-client-design.md`

---

## File Structure

- `src/vibing_cli/__init__.py` — modify: mount `runtime` group + 4 client groups.
- `src/vibing_cli/client/__init__.py` — create: package marker.
- `src/vibing_cli/client/http.py` — create: env base URL, `request()`, error rendering.
- `src/vibing_cli/client/render.py` — create: `render()` + `JsonOption` + shared `console`.
- `src/vibing_cli/client/devcontainers.py` — create: devcontainer app + nested `session` app.
- `src/vibing_cli/client/inbox.py` — create: inbox app.
- `src/vibing_cli/client/approvals.py` — create: approvals app.
- `src/vibing_cli/client/system.py` — create: system reads app.
- `src/vibing_cli/CLAUDE.md` — modify: update command list.
- `tests/cli/__init__.py` — create.
- `tests/cli/conftest.py` — create: `patch_api` fixture (MockTransport injection).
- `tests/cli/test_runtime_group.py` — create.
- `tests/cli/test_http.py` — create.
- `tests/cli/test_devcontainers.py` — create.
- `tests/cli/test_sessions.py` — create.
- `tests/cli/test_inbox_approvals_system.py` — create.
- `tests/api/test_cli.py` — modify: existing root-help test asserts old flat names.

---

## Task 1: Regroup runtime workers under `vibing runtime`

**Files:**
- Modify: `src/vibing_cli/__init__.py`
- Modify: `tests/api/test_cli.py:14-19` (the `test_root_cli_exposes_runtime_subcommands` test)

- [ ] **Step 1: Update the existing root-help test to expect the new group**

Replace the body of `test_root_cli_exposes_runtime_subcommands` in `tests/api/test_cli.py`:

```python
def test_root_cli_exposes_runtime_subcommands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "runtime" in result.output
    assert "host-runtime" not in result.output
    assert "devcontainer-runtime" not in result.output


def test_runtime_group_exposes_host_and_devcontainer() -> None:
    result = runner.invoke(app, ["runtime", "--help"])

    assert result.exit_code == 0, result.output
    assert "host" in result.output
    assert "devcontainer" in result.output
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/api/test_cli.py::test_runtime_group_exposes_host_and_devcontainer -v`
Expected: FAIL — `runtime` group not mounted (exit_code != 0).

- [ ] **Step 3: Rewrite the root app to mount the `runtime` group**

Replace the entire contents of `src/vibing_cli/__init__.py`:

```python
import typer

from vibing_api.cli import dev_app
from vibing_cli.client import approvals, devcontainers, inbox, system
from vibing_devcontainer_runtime.cli import cli as devcontainer_runtime_app
from vibing_host_runtime.cli import cli as host_runtime_app

app = typer.Typer(name="vibing", help="Vibing CLI.", no_args_is_help=True)

app.add_typer(dev_app, name="dev")

runtime_app = typer.Typer(help="Run long-lived runtime workers.", no_args_is_help=True)
runtime_app.add_typer(host_runtime_app, name="host")
runtime_app.add_typer(devcontainer_runtime_app, name="devcontainer")
app.add_typer(runtime_app, name="runtime")

app.add_typer(devcontainers.app, name="devcontainer")
app.add_typer(inbox.app, name="inbox")
app.add_typer(approvals.app, name="approval")
app.add_typer(system.app, name="system")
```

Note: this imports `vibing_cli.client.*`, which is created in later tasks. To keep Task 1
runnable on its own, create empty stub modules now (they get real content in Tasks 3–6):

```bash
mkdir -p src/vibing_cli/client
touch src/vibing_cli/client/__init__.py
printf 'import typer\n\napp = typer.Typer(no_args_is_help=True)\n' > src/vibing_cli/client/devcontainers.py
printf 'import typer\n\napp = typer.Typer(no_args_is_help=True)\n' > src/vibing_cli/client/inbox.py
printf 'import typer\n\napp = typer.Typer(no_args_is_help=True)\n' > src/vibing_cli/client/approvals.py
printf 'import typer\n\napp = typer.Typer(no_args_is_help=True)\n' > src/vibing_cli/client/system.py
```

- [ ] **Step 4: Run the runtime-group tests to verify they pass**

Run: `uv run pytest tests/api/test_cli.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_cli/__init__.py src/vibing_cli/client tests/api/test_cli.py
git commit -m "refactor: group runtime workers under 'vibing runtime'"
```

---

## Task 2: Test scaffolding — runtime group smoke tests

**Files:**
- Create: `tests/cli/__init__.py`
- Create: `tests/cli/test_runtime_group.py`

(The `patch_api` fixture / `conftest.py` is created in Task 3, after `http.py` exists — a
`conftest.py` importing `http` now would break collection of every test in `tests/cli/`.)

- [ ] **Step 1: Create the test package marker**

Create `tests/cli/__init__.py` (empty file).

- [ ] **Step 2: Add a smoke test for the runtime group help (no fixture needed)**

Create `tests/cli/test_runtime_group.py`:

```python
from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()


def test_runtime_host_help() -> None:
    result = runner.invoke(app, ["runtime", "host", "--help"])
    assert result.exit_code == 0, result.output
    assert "--control-plane-url" in result.output


def test_runtime_devcontainer_help() -> None:
    result = runner.invoke(app, ["runtime", "devcontainer", "--help"])
    assert result.exit_code == 0, result.output
    assert "--devcontainer-id" in result.output


def test_old_flat_names_removed() -> None:
    assert runner.invoke(app, ["host-runtime", "--help"]).exit_code != 0
    assert runner.invoke(app, ["devcontainer-runtime", "--help"]).exit_code != 0
```

- [ ] **Step 3: Run the runtime smoke tests**

Run: `uv run pytest tests/cli/test_runtime_group.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/cli/__init__.py tests/cli/test_runtime_group.py
git commit -m "test: add cli test scaffolding and runtime group smoke tests"
```

---

## Task 3: `client/http.py` — base URL + request + error rendering

**Files:**
- Create: `src/vibing_cli/client/http.py` (not stubbed in Task 1; created fresh here)
- Create: `tests/cli/conftest.py` (the `patch_api` fixture, used by Tasks 3–6)
- Test: `tests/cli/test_http.py`

- [ ] **Step 1: Create the `patch_api` fixture**

Create `tests/cli/conftest.py`:

```python
from collections.abc import Callable

import httpx
import pytest

from vibing_cli.client import http


@pytest.fixture
def patch_api(monkeypatch: pytest.MonkeyPatch) -> Callable[[Callable[[httpx.Request], httpx.Response]], None]:
    """Route the client's HTTP calls through an in-memory MockTransport handler."""

    def _patch(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        transport = httpx.MockTransport(handler)

        def get_client() -> httpx.Client:
            return httpx.Client(base_url=http.base_url(), transport=transport)

        monkeypatch.setattr(http, "get_client", get_client)

    return _patch
```

- [ ] **Step 2: Write failing tests**

Create `tests/cli/test_http.py`:

```python
import httpx
import pytest
import typer

from vibing_cli.client import http


def test_base_url_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBING_API_URL", raising=False)
    monkeypatch.delenv("VIBING_API_V1_PREFIX", raising=False)
    assert http.base_url() == "http://localhost:8080/api/v1"


def test_base_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIBING_API_URL", "http://host.docker.internal:9000/")
    monkeypatch.setenv("VIBING_API_V1_PREFIX", "/api/v1")
    assert http.base_url() == "http://host.docker.internal:9000/api/v1"


def test_request_returns_json_on_success(patch_api) -> None:
    patch_api(lambda request: httpx.Response(200, json={"ok": True}))
    assert http.request("GET", "/status") == {"ok": True}


def test_request_returns_none_on_204(patch_api) -> None:
    patch_api(lambda request: httpx.Response(204))
    assert http.request("DELETE", "/devcontainers/x") is None


def test_request_raises_exit_on_error_envelope(patch_api, capsys: pytest.CaptureFixture[str]) -> None:
    patch_api(
        lambda request: httpx.Response(
            404, json={"error": {"code": "DEVCONTAINER_NOT_FOUND", "message": "nope", "details": None}}
        )
    )
    with pytest.raises(typer.Exit) as exc:
        http.request("GET", "/devcontainers/x")
    assert exc.value.exit_code == 1
    assert "DEVCONTAINER_NOT_FOUND" in capsys.readouterr().err


def test_request_raises_exit_on_connect_error(patch_api, capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    patch_api(handler)
    with pytest.raises(typer.Exit) as exc:
        http.request("GET", "/status")
    assert exc.value.exit_code == 1
    assert "Cannot reach API" in capsys.readouterr().err
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/cli/test_http.py -v`
Expected: FAIL — `http.base_url` / `http.request` not defined (ImportError/AttributeError).

- [ ] **Step 4: Implement `http.py`**

Create `src/vibing_cli/client/http.py`:

```python
import os
from typing import Any

import httpx
import typer
from rich.console import Console

_err = Console(stderr=True)

DEFAULT_API_URL = "http://localhost:8080"
DEFAULT_API_V1_PREFIX = "/api/v1"


def base_url() -> str:
    root = os.environ.get("VIBING_API_URL", DEFAULT_API_URL).rstrip("/")
    prefix = os.environ.get("VIBING_API_V1_PREFIX", DEFAULT_API_V1_PREFIX)
    return f"{root}{prefix}"


def get_client() -> httpx.Client:
    return httpx.Client(base_url=base_url(), timeout=30.0)


def request(
    method: str,
    path: str,
    *,
    json: Any | None = None,
    params: dict[str, str] | None = None,
) -> Any:
    """Call the API and return parsed JSON (or None for empty/204). Exit 1 on failure."""
    try:
        with get_client() as client:
            response = client.request(method, path, json=json, params=params)
    except httpx.ConnectError:
        _err.print(f"[red]Cannot reach API at {base_url()}[/red]")
        raise typer.Exit(1) from None

    if response.is_success:
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    _render_error(response)
    raise typer.Exit(1)


def _render_error(response: httpx.Response) -> None:
    try:
        error = response.json()["error"]
        _err.print(f"[red]{error['code']}: {error['message']}[/red]")
    except (ValueError, KeyError, TypeError):
        _err.print(f"[red]HTTP {response.status_code}: {response.text}[/red]")
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/cli/test_http.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vibing_cli/client/http.py tests/cli/conftest.py tests/cli/test_http.py
git commit -m "feat: add client http helper with env base url and error rendering"
```

---

## Task 4: `client/render.py` — output rendering + `JsonOption`

**Files:**
- Create: `src/vibing_cli/client/render.py`
- Test: covered indirectly by resource tests; add a focused unit test in `tests/cli/test_http.py` is NOT needed — add `tests/cli/test_render.py`.

- [ ] **Step 1: Write failing tests**

Create `tests/cli/test_render.py`:

```python
import json

from vibing_cli.client import render


def test_render_json_outputs_raw(capsys) -> None:
    render.render({"id": "x"}, as_json=True)
    assert json.loads(capsys.readouterr().out) == {"id": "x"}


def test_render_list_prints_table(capsys) -> None:
    render.render({"items": [{"id": "a", "name": "one"}]}, as_json=False)
    out = capsys.readouterr().out
    assert "id" in out and "name" in out and "one" in out


def test_render_empty_list(capsys) -> None:
    render.render({"items": []}, as_json=False)
    assert "No results" in capsys.readouterr().out


def test_render_object_prints_fields(capsys) -> None:
    render.render({"id": "x", "status": "running"}, as_json=False)
    out = capsys.readouterr().out
    assert "status" in out and "running" in out


def test_render_none_is_silent(capsys) -> None:
    render.render(None, as_json=False)
    assert capsys.readouterr().out == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_render.py -v`
Expected: FAIL — `render` module/function not defined.

- [ ] **Step 3: Implement `render.py`**

Create `src/vibing_cli/client/render.py`:

```python
import json as _json
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

console = Console()

JsonOption = Annotated[bool, typer.Option("--json", help="Raw JSON output.")]


def render(data: Any, as_json: bool) -> None:
    if as_json:
        console.print_json(_json.dumps(data))
        return
    if data is None:
        return
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        _render_list(data["items"])
    elif isinstance(data, list):
        _render_list(data)
    else:
        _render_object(data)


def _render_list(items: list[dict[str, Any]]) -> None:
    if not items:
        console.print("[dim]No results.[/dim]")
        return
    columns = list(items[0].keys())
    table = Table(*columns)
    for item in items:
        table.add_row(*(str(item.get(column, "")) for column in columns))
    console.print(table)


def _render_object(obj: dict[str, Any]) -> None:
    table = Table(show_header=False)
    table.add_column("field", style="bold")
    table.add_column("value")
    for key, value in obj.items():
        table.add_row(key, str(value))
    console.print(table)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/cli/test_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_cli/client/render.py tests/cli/test_render.py
git commit -m "feat: add client output rendering and --json option"
```

---

## Task 5: `client/devcontainers.py` — devcontainer + nested session apps

**Files:**
- Create: `src/vibing_cli/client/devcontainers.py` (replaces the Task 1 stub)
- Test: `tests/cli/test_devcontainers.py`, `tests/cli/test_sessions.py`

- [ ] **Step 1: Write failing devcontainer tests**

Create `tests/cli/test_devcontainers.py`:

```python
import json

import httpx
from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()

_DC = {
    "id": "dc_1",
    "name": "sandbox",
    "local_path": "/p",
    "status": "created",
    "created_at": "t",
    "updated_at": "t",
}


def test_add_posts_name_and_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json=_DC)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "add", "sandbox", "-d", "/p"])

    assert result.exit_code == 0, result.output
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/devcontainers"
    assert seen["body"] == {"name": "sandbox", "local_path": "/p"}


def test_ls_renders_table(patch_api) -> None:
    patch_api(lambda request: httpx.Response(200, json={"items": [_DC]}))
    result = runner.invoke(app, ["devcontainer", "ls"])
    assert result.exit_code == 0, result.output
    assert "sandbox" in result.output


def test_get_json(patch_api) -> None:
    patch_api(lambda request: httpx.Response(200, json=_DC))
    result = runner.invoke(app, ["devcontainer", "get", "dc_1", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["id"] == "dc_1"


def test_update_sends_only_set_fields(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_DC)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "update", "dc_1", "--name", "new"])
    assert result.exit_code == 0, result.output
    assert seen["method"] == "PATCH"
    assert seen["body"] == {"name": "new"}


def test_rm_calls_delete(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(204)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "rm", "dc_1"])
    assert result.exit_code == 0, result.output
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/v1/devcontainers/dc_1"


def test_start_posts_to_start(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(202, json=_DC)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "start", "dc_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/start"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_devcontainers.py -v`
Expected: FAIL — commands not defined (the Task 1 stub has no commands).

- [ ] **Step 3: Implement `devcontainers.py`**

Create `src/vibing_cli/client/devcontainers.py` (overwrite the stub):

```python
from enum import Enum
from typing import Annotated

import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, console, render

app = typer.Typer(help="Manage devcontainers via the API.", no_args_is_help=True)
session_app = typer.Typer(help="Manage agent sessions via the API.", no_args_is_help=True)
app.add_typer(session_app, name="session")

_BASE = "/devcontainers"


class Resolution(str, Enum):
    approved = "approved"
    rejected = "rejected"


@app.command("add")
def add(
    name: str,
    local_path: Annotated[str, typer.Option("-d", "--local-path", help="Local project path.")],
    json_: JsonOption = False,
) -> None:
    """Create a devcontainer."""
    render(request("POST", _BASE, json={"name": name, "local_path": local_path}), json_)


@app.command("ls")
def ls(json_: JsonOption = False) -> None:
    """List devcontainers."""
    render(request("GET", _BASE), json_)


@app.command("get")
def get(devcontainer_id: str, json_: JsonOption = False) -> None:
    """Show one devcontainer."""
    render(request("GET", f"{_BASE}/{devcontainer_id}"), json_)


@app.command("update")
def update(
    devcontainer_id: str,
    name: Annotated[str | None, typer.Option("--name")] = None,
    status: Annotated[str | None, typer.Option("--status")] = None,
    json_: JsonOption = False,
) -> None:
    """Update a devcontainer's name or status."""
    body = {key: value for key, value in {"name": name, "status": status}.items() if value is not None}
    render(request("PATCH", f"{_BASE}/{devcontainer_id}", json=body), json_)


@app.command("rm")
def rm(devcontainer_id: str) -> None:
    """Delete a devcontainer."""
    request("DELETE", f"{_BASE}/{devcontainer_id}")
    console.print(f"[green]Deleted {devcontainer_id}.[/green]")


@app.command("start")
def start(devcontainer_id: str, json_: JsonOption = False) -> None:
    """Start a devcontainer."""
    render(request("POST", f"{_BASE}/{devcontainer_id}/start"), json_)


@app.command("stop")
def stop(devcontainer_id: str, json_: JsonOption = False) -> None:
    """Stop a devcontainer."""
    render(request("POST", f"{_BASE}/{devcontainer_id}/stop"), json_)


@session_app.command("start")
def session_start(
    devcontainer_id: str,
    prompt: Annotated[str, typer.Option("-p", "--prompt", help="Agent prompt.")],
    json_: JsonOption = False,
) -> None:
    """Start an agent session."""
    render(
        request("POST", f"{_BASE}/{devcontainer_id}/agent-sessions", json={"prompt": prompt}),
        json_,
    )


@session_app.command("stop")
def session_stop(devcontainer_id: str, session_id: str, json_: JsonOption = False) -> None:
    """Stop an agent session."""
    render(
        request("POST", f"{_BASE}/{devcontainer_id}/agent-sessions/{session_id}/stop"),
        json_,
    )


@session_app.command("input")
def session_input(
    devcontainer_id: str,
    session_id: str,
    inbox_event: Annotated[str, typer.Option("--inbox-event", help="Inbox event id to answer.")],
    text: Annotated[str, typer.Option("--text", help="User input text.")],
    json_: JsonOption = False,
) -> None:
    """Answer an agent question."""
    render(
        request(
            "POST",
            f"{_BASE}/{devcontainer_id}/agent-sessions/{session_id}/user-input",
            json={"inbox_event_id": inbox_event, "text": text},
        ),
        json_,
    )


@session_app.command("resolve")
def session_resolve(
    devcontainer_id: str,
    session_id: str,
    approval: Annotated[str, typer.Option("--approval", help="Approval request id.")],
    resolution: Annotated[Resolution, typer.Option("--resolution")],
    json_: JsonOption = False,
) -> None:
    """Resolve a pending approval."""
    render(
        request(
            "POST",
            f"{_BASE}/{devcontainer_id}/agent-sessions/{session_id}/approval-resolution",
            json={"approval_request_id": approval, "resolution": resolution.value},
        ),
        json_,
    )
```

- [ ] **Step 4: Run devcontainer tests to verify pass**

Run: `uv run pytest tests/cli/test_devcontainers.py -v`
Expected: PASS.

- [ ] **Step 5: Write failing session tests**

Create `tests/cli/test_sessions.py`:

```python
import json

import httpx
from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()

_SESSION = {
    "id": "as_1",
    "devcontainer_id": "dc_1",
    "status": "starting",
    "started_at": None,
    "ended_at": None,
    "last_event_at": None,
    "created_at": "t",
    "updated_at": "t",
}


def test_session_start_posts_prompt(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json=_SESSION)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "session", "start", "dc_1", "-p", "do it"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/agent-sessions"
    assert seen["body"] == {"prompt": "do it"}


def test_session_input_body(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json=_SESSION)

    patch_api(handler)
    result = runner.invoke(
        app,
        ["devcontainer", "session", "input", "dc_1", "as_1", "--inbox-event", "ib_1", "--text", "yes"],
    )
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/agent-sessions/as_1/user-input"
    assert seen["body"] == {"inbox_event_id": "ib_1", "text": "yes"}


def test_session_resolve_body(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json=_SESSION)

    patch_api(handler)
    result = runner.invoke(
        app,
        ["devcontainer", "session", "resolve", "dc_1", "as_1", "--approval", "ap_1", "--resolution", "approved"],
    )
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/agent-sessions/as_1/approval-resolution"
    assert seen["body"] == {"approval_request_id": "ap_1", "resolution": "approved"}


def test_session_resolve_rejects_bad_value(patch_api) -> None:
    patch_api(lambda request: httpx.Response(202, json=_SESSION))
    result = runner.invoke(
        app,
        ["devcontainer", "session", "resolve", "dc_1", "as_1", "--approval", "ap_1", "--resolution", "maybe"],
    )
    assert result.exit_code != 0
```

- [ ] **Step 6: Run session tests to verify pass**

Run: `uv run pytest tests/cli/test_sessions.py -v`
Expected: PASS (including the invalid-`--resolution` case, rejected by the `Resolution` enum).

- [ ] **Step 7: Commit**

```bash
git add src/vibing_cli/client/devcontainers.py tests/cli/test_devcontainers.py tests/cli/test_sessions.py
git commit -m "feat: add devcontainer and agent-session client commands"
```

---

## Task 6: `inbox`, `approvals`, `system` apps

**Files:**
- Create: `src/vibing_cli/client/inbox.py` (overwrite stub)
- Create: `src/vibing_cli/client/approvals.py` (overwrite stub)
- Create: `src/vibing_cli/client/system.py` (overwrite stub)
- Test: `tests/cli/test_inbox_approvals_system.py`

- [ ] **Step 1: Write failing tests**

Create `tests/cli/test_inbox_approvals_system.py`:

```python
import httpx
from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()


def test_inbox_ls_passes_filters(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    patch_api(handler)
    result = runner.invoke(app, ["inbox", "ls", "--status", "pending", "--devcontainer", "dc_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/inbox-events"
    assert seen["params"] == {"status": "pending", "devcontainer_id": "dc_1"}


def test_inbox_get_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"id": "ib_1"})

    patch_api(handler)
    result = runner.invoke(app, ["inbox", "get", "ib_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/inbox-events/ib_1"


def test_approval_ls_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"items": []})

    patch_api(handler)
    result = runner.invoke(app, ["approval", "ls"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/approval-requests"


def test_approval_get_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"id": "ap_1"})

    patch_api(handler)
    result = runner.invoke(app, ["approval", "get", "ap_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/approval-requests/ap_1"


def test_system_status_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"status": "ok"})

    patch_api(handler)
    result = runner.invoke(app, ["system", "status"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/status"


def test_system_health_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"status": "ok"})

    patch_api(handler)
    result = runner.invoke(app, ["system", "health"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/health"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_inbox_approvals_system.py -v`
Expected: FAIL — commands not defined on the stub apps.

- [ ] **Step 3: Implement `inbox.py`**

Create `src/vibing_cli/client/inbox.py` (overwrite stub):

```python
from typing import Annotated

import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, render

app = typer.Typer(help="Inspect inbox events via the API.", no_args_is_help=True)

_BASE = "/inbox-events"


@app.command("ls")
def ls(
    status: Annotated[str | None, typer.Option("--status")] = None,
    devcontainer: Annotated[str | None, typer.Option("--devcontainer")] = None,
    session: Annotated[str | None, typer.Option("--session")] = None,
    json_: JsonOption = False,
) -> None:
    """List inbox events, optionally filtered."""
    params = {
        key: value
        for key, value in {
            "status": status,
            "devcontainer_id": devcontainer,
            "agent_session_id": session,
        }.items()
        if value is not None
    }
    render(request("GET", _BASE, params=params), json_)


@app.command("get")
def get(inbox_event_id: str, json_: JsonOption = False) -> None:
    """Show one inbox event with detail."""
    render(request("GET", f"{_BASE}/{inbox_event_id}"), json_)
```

- [ ] **Step 4: Implement `approvals.py`**

Create `src/vibing_cli/client/approvals.py` (overwrite stub):

```python
import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, render

app = typer.Typer(help="Inspect approval requests via the API.", no_args_is_help=True)

_BASE = "/approval-requests"


@app.command("ls")
def ls(json_: JsonOption = False) -> None:
    """List approval requests."""
    render(request("GET", _BASE), json_)


@app.command("get")
def get(approval_request_id: str, json_: JsonOption = False) -> None:
    """Show one approval request."""
    render(request("GET", f"{_BASE}/{approval_request_id}"), json_)
```

- [ ] **Step 5: Implement `system.py`**

Create `src/vibing_cli/client/system.py` (overwrite stub):

```python
import typer

from vibing_cli.client.http import request
from vibing_cli.client.render import JsonOption, render

app = typer.Typer(help="Read control-plane status endpoints.", no_args_is_help=True)


@app.command("status")
def status(json_: JsonOption = False) -> None:
    """Show control-plane status."""
    render(request("GET", "/status"), json_)


@app.command("diagnostics")
def diagnostics(json_: JsonOption = False) -> None:
    """Show diagnostics."""
    render(request("GET", "/diagnostics"), json_)


@app.command("config")
def config(json_: JsonOption = False) -> None:
    """Show runtime config."""
    render(request("GET", "/config"), json_)


@app.command("settings")
def settings(json_: JsonOption = False) -> None:
    """Show settings."""
    render(request("GET", "/settings"), json_)


@app.command("health")
def health(json_: JsonOption = False) -> None:
    """Show health."""
    render(request("GET", "/health"), json_)
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest tests/cli/test_inbox_approvals_system.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vibing_cli/client/inbox.py src/vibing_cli/client/approvals.py src/vibing_cli/client/system.py tests/cli/test_inbox_approvals_system.py
git commit -m "feat: add inbox, approval, and system client commands"
```

---

## Task 7: Docs + full check sweep

**Files:**
- Modify: `src/vibing_cli/CLAUDE.md`

- [ ] **Step 1: Update `src/vibing_cli/CLAUDE.md`**

Replace the file contents:

```markdown
# vibing_cli

Root Typer command aggregator. Public command: `vibing`.

## Files

- `__init__.py`: creates root app and mounts subcommands.
- `client/`: HTTP-client commands that drive the running API (`httpx`).
  - `http.py`: env base URL (`VIBING_API_URL` + `VIBING_API_V1_PREFIX`), `request()`, error rendering.
  - `render.py`: rich table/object rendering + shared `--json` option.
  - `devcontainers.py`: `vibing devcontainer ...` incl. nested `session` sub-app.
  - `inbox.py`, `approvals.py`, `system.py`: read endpoints.

## Commands

- `vibing dev ...`: from `vibing_api.cli`.
- `vibing runtime host ...`: host runtime worker (`vibing_host_runtime.cli`).
- `vibing runtime devcontainer ...`: agent runtime worker (`vibing_devcontainer_runtime.cli`).
- `vibing devcontainer ...`: devcontainer CRUD + lifecycle + `session` agent commands.
- `vibing inbox ...` / `vibing approval ...` / `vibing system ...`: read endpoints.

## Context

- Client commands call the live API; base URL from env. Inside the devcontainer set
  `VIBING_API_URL=http://host.docker.internal:8080` to reach the host-published API.
- No domain logic here; client modules are thin HTTP glue.
- Tests: `tests/cli/`, plus `tests/api/test_cli.py` and runtime CLI tests.
```

- [ ] **Step 2: Run ruff lint**

Run: `uv run ruff check src tests`
Expected: PASS (no errors). Fix any reported issues, then re-run.

- [ ] **Step 3: Run ruff format check**

Run: `uv run ruff format --check src tests`
Expected: PASS. If it fails, run `uv run ruff format src tests` and re-check.

- [ ] **Step 4: Run mypy**

Run: `uv run mypy src`
Expected: PASS (no type errors).

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS (all tests).

- [ ] **Step 6: Manual smoke (optional, needs a running API)**

Run: `uv run vibing devcontainer ls` (with the API up, or expect the "Cannot reach API" message and exit 1 when it's down).
Expected: a rendered table, or the friendly connection error.

- [ ] **Step 7: Commit**

```bash
git add src/vibing_cli/CLAUDE.md
git commit -m "docs: update vibing_cli CLAUDE.md for runtime group and client commands"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** every endpoint in the spec table maps to a command (Tasks 5–6); runtime regroup is Task 1; env base URL + error rendering is Task 3; `--json` + rendering is Task 4; docs are Task 7.
- **Stub ordering:** Task 1 creates minimal stubs for `devcontainers/inbox/approvals/system` so the root import works; Tasks 5–6 overwrite them with real commands. Don't skip the stub step or Task 1's tests won't run.
- **Type names are consistent across tasks:** `http.request`, `http.base_url`, `http.get_client`, `render.render`, `render.JsonOption`, `render.console`, `Resolution` enum.
- **Why `Resolution` enum:** gives Typer built-in choice validation for `--resolution` (approved/rejected) — no hand-rolled checks.
