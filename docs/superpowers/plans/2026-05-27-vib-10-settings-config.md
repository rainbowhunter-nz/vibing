# VIB-10 Settings/Config Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a persisted, editable user-settings foundation — a settings model, JSON-file persistence, `GET`/`PATCH` endpoints, and a real settings page — where only the workspace storage location is editable and everything else is read-only or an honest placeholder.

**Architecture:** A user-settings concept distinct from the existing env-driven `Settings` class. The one editable preference persists to a JSON file on disk; the `GET` response is assembled from the file (storage location), env config (host/port), placeholder defaults (editor/notification), and a runtime-detection stub (all null). The frontend rewrites the `Settings.tsx` placeholder into a sectioned page following the established typed-fetch + discriminated-union state pattern.

**Tech Stack:** FastAPI, pydantic / pydantic-settings, raw JSON file I/O (no DB for settings), pytest (backend); React 19 + Vite + TypeScript + Tailwind v4 (frontend, no test runner — `pnpm build` + manual check).

**Spec:** `docs/superpowers/specs/2026-05-27-vib-10-settings-config-design.md`

---

## File Structure

Backend (`apps/api/`):
- **Modify** `src/vibing_api/core/config.py` — add `backend_host`, `backend_port`, `settings_file` env fields.
- **Create** `src/vibing_api/core/settings_store.py` — `StoredSettings` model + `load`/`update`/`default_storage_location` (JSON file persistence).
- **Create** `src/vibing_api/api/routes/settings.py` — `RuntimeDetection`, `SettingsResponse`, `SettingsUpdate`, `detect_runtimes()` stub, `GET`/`PATCH` handlers.
- **Modify** `src/vibing_api/main.py` — register the settings router.
- **Modify** `tests/conftest.py` — add a `settings_file` fixture.
- **Create** `tests/test_settings.py` — endpoint tests.
- **Modify** `tests/test_config.py` — assert the new config defaults.

Deployment:
- **Modify** `Dockerfile` — point `VIBING_SETTINGS_FILE` at the `/data` volume.

Frontend (`apps/web/`):
- **Modify** `src/lib/api.ts` — settings types + `sendJson` helper + `fetchSettings`/`updateSettings`.
- **Modify** `src/routes/Settings.tsx` — rewrite placeholder into the real settings page.

**Note on working directory:** backend commands run from `apps/api/`; frontend commands run from `apps/web/`. Commands below include the `cd`.

---

## Task 1: Add user-settings env fields to `Settings`

**Files:**
- Modify: `apps/api/src/vibing_api/core/config.py`
- Test: `apps/api/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_config.py`. First add this import near the top (below the existing `from fastapi.testclient import TestClient`):

```python
from vibing_api.core.config import settings
```

Then append this test:

```python
def test_settings_has_backend_host_port_and_settings_file() -> None:
    assert settings.backend_host == "0.0.0.0"
    assert settings.backend_port == 8080
    assert settings.settings_file.endswith("settings.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/test_config.py::test_settings_has_backend_host_port_and_settings_file -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'backend_host'`.

- [ ] **Step 3: Write minimal implementation**

Replace the body of `apps/api/src/vibing_api/core/config.py` with:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VIBING_",
        extra="ignore",
    )

    app_name: str = "vibing-api"
    api_v1_prefix: str = "/api/v1"

    database_url: str = f"sqlite:///{Path.cwd() / 'vibing.db'}"
    static_dir: str | None = None

    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    settings_file: str = str(Path.home() / ".vibing" / "settings.json")


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/test_config.py -v`
Expected: PASS (all config tests).

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/vibing_api/core/config.py apps/api/tests/test_config.py
git commit -m "feat(api): add backend host/port and settings file to config"
```

---

## Task 2: JSON-file settings store

**Files:**
- Create: `apps/api/src/vibing_api/core/settings_store.py`
- Modify: `apps/api/tests/conftest.py`
- Test: `apps/api/tests/test_settings_store.py`

- [ ] **Step 1: Add the `settings_file` fixture**

Append to `apps/api/tests/conftest.py` (the file already imports `settings`, `Path`, `pytest`):

```python
@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "vibing-settings.json"
    monkeypatch.setattr(settings, "settings_file", str(path))
    return path
```

- [ ] **Step 2: Write the failing tests**

Create `apps/api/tests/test_settings_store.py`:

```python
import json
from pathlib import Path

from vibing_api.core import settings_store


def test_load_returns_default_when_file_missing(settings_file: Path) -> None:
    assert not settings_file.exists()
    stored = settings_store.load()
    assert stored.workspace_storage_location == str(settings_file.parent / "workspaces")


def test_update_writes_file_and_load_reads_it(settings_file: Path) -> None:
    settings_store.update("/tmp/ws-a")
    assert json.loads(settings_file.read_text())["workspace_storage_location"] == "/tmp/ws-a"
    assert settings_store.load().workspace_storage_location == "/tmp/ws-a"


def test_load_ignores_unknown_keys(settings_file: Path) -> None:
    settings_file.write_text(
        json.dumps({"workspace_storage_location": "/tmp/ws-b", "bogus": 1})
    )
    assert settings_store.load().workspace_storage_location == "/tmp/ws-b"


def test_load_falls_back_to_default_on_malformed_file(settings_file: Path) -> None:
    settings_file.write_text("not json{")
    assert settings_store.load().workspace_storage_location == str(
        settings_file.parent / "workspaces"
    )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/test_settings_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vibing_api.core.settings_store'`.

- [ ] **Step 4: Write minimal implementation**

Create `apps/api/src/vibing_api/core/settings_store.py`:

```python
"""JSON-file persistence for user-facing settings.

Distinct from the env-driven `Settings` (process config). Only the editable
preference (workspace storage location) is persisted here.
"""

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from vibing_api.core.config import settings


class StoredSettings(BaseModel):
    workspace_storage_location: str


def _path() -> Path:
    return Path(settings.settings_file)


def default_storage_location() -> str:
    return str(_path().parent / "workspaces")


def load() -> StoredSettings:
    path = _path()
    data: dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            loaded = None
        if isinstance(loaded, dict):
            data = loaded
    raw = data.get("workspace_storage_location")
    location = raw if isinstance(raw, str) and raw.strip() else default_storage_location()
    return StoredSettings(workspace_storage_location=location)


def update(workspace_storage_location: str) -> StoredSettings:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"workspace_storage_location": workspace_storage_location}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return StoredSettings(workspace_storage_location=workspace_storage_location)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_settings_store.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/vibing_api/core/settings_store.py apps/api/tests/conftest.py apps/api/tests/test_settings_store.py
git commit -m "feat(api): add JSON-file settings store"
```

---

## Task 3: `GET /api/v1/settings` endpoint + router registration

**Files:**
- Create: `apps/api/src/vibing_api/api/routes/settings.py`
- Modify: `apps/api/src/vibing_api/main.py`
- Test: `apps/api/tests/test_settings.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_settings.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings


def test_get_returns_defaults_when_no_file(client: TestClient, settings_file: Path) -> None:
    assert not settings_file.exists()
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["workspace_storage_location"] == str(settings_file.parent / "workspaces")
    assert body["editor_preference"] is None
    assert body["notifications_enabled"] is None
    assert body["runtime"] == {
        "docker": None,
        "podman": None,
        "devcontainer_cli": None,
        "claude_code": None,
    }


def test_get_reflects_backend_host_and_port(
    client: TestClient, settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "backend_host", "127.0.0.1")
    monkeypatch.setattr(settings, "backend_port", 9000)
    body = client.get("/api/v1/settings").json()
    assert body["backend_host"] == "127.0.0.1"
    assert body["backend_port"] == 9000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/test_settings.py -v`
Expected: FAIL — the route does not exist yet, so `GET /api/v1/settings` returns 404 (`status_code == 200` assertion fails).

- [ ] **Step 3: Create the settings route**

Create `apps/api/src/vibing_api/api/routes/settings.py`:

```python
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, field_validator

from vibing_api.core import settings_store
from vibing_api.core.config import settings

router = APIRouter(tags=["settings"])


class RuntimeDetection(BaseModel):
    docker: bool | None = None
    podman: bool | None = None
    devcontainer_cli: bool | None = None
    claude_code: bool | None = None


class SettingsResponse(BaseModel):
    workspace_storage_location: str
    backend_host: str
    backend_port: int
    editor_preference: str | None = None
    notifications_enabled: bool | None = None
    runtime: RuntimeDetection


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_storage_location: str

    @field_validator("workspace_storage_location")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("workspace_storage_location must not be empty")
        return value


def detect_runtimes() -> RuntimeDetection:
    # Detection lands in a later ticket; the fields exist now, all unknown.
    return RuntimeDetection()


def _build_response(stored: settings_store.StoredSettings) -> SettingsResponse:
    return SettingsResponse(
        workspace_storage_location=stored.workspace_storage_location,
        backend_host=settings.backend_host,
        backend_port=settings.backend_port,
        editor_preference=None,
        notifications_enabled=None,
        runtime=detect_runtimes(),
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return _build_response(settings_store.load())
```

- [ ] **Step 4: Register the router in `main.py`**

In `apps/api/src/vibing_api/main.py`, update the routes import line:

```python
from vibing_api.api.routes import config, health, settings as settings_route, status, workspaces
```

(`settings as settings_route` avoids colliding with the `settings` config instance imported just below.)

Then add the new router to the registration loop:

```python
    for router in (
        health.router,
        status.router,
        config.router,
        workspaces.router,
        settings_route.router,
    ):
        app.include_router(router, prefix=settings.api_v1_prefix)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_settings.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/vibing_api/api/routes/settings.py apps/api/src/vibing_api/main.py apps/api/tests/test_settings.py
git commit -m "feat(api): add GET /settings endpoint and register router"
```

---

## Task 4: `PATCH /api/v1/settings` endpoint

**Files:**
- Modify: `apps/api/src/vibing_api/api/routes/settings.py`
- Test: `apps/api/tests/test_settings.py`

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_settings.py` (add `import json` at the top of the file, and `from vibing_api.main import create_app`):

```python
def test_patch_persists_and_roundtrips(client: TestClient, settings_file: Path) -> None:
    response = client.patch(
        "/api/v1/settings", json={"workspace_storage_location": "/tmp/ws"}
    )
    assert response.status_code == 200
    assert response.json()["workspace_storage_location"] == "/tmp/ws"
    assert json.loads(settings_file.read_text())["workspace_storage_location"] == "/tmp/ws"
    assert client.get("/api/v1/settings").json()["workspace_storage_location"] == "/tmp/ws"


def test_patch_survives_restart(client: TestClient, settings_file: Path) -> None:
    client.patch("/api/v1/settings", json={"workspace_storage_location": "/tmp/persist"})
    with TestClient(create_app()) as fresh:
        body = fresh.get("/api/v1/settings").json()
    assert body["workspace_storage_location"] == "/tmp/persist"


def test_patch_rejects_empty_value(client: TestClient, settings_file: Path) -> None:
    response = client.patch(
        "/api/v1/settings", json={"workspace_storage_location": "   "}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_rejects_unknown_field(client: TestClient, settings_file: Path) -> None:
    response = client.patch(
        "/api/v1/settings",
        json={"workspace_storage_location": "/tmp/ws", "backend_host": "0.0.0.0"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
```

Update the import block at the top of the file so it reads:

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.main import create_app
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && uv run pytest tests/test_settings.py -k patch -v`
Expected: FAIL — `PATCH /api/v1/settings` is not defined, so it returns 405/404 (the `status_code == 200` and 422 assertions fail).

- [ ] **Step 3: Add the PATCH handler**

Append to `apps/api/src/vibing_api/api/routes/settings.py` (after `get_settings`):

```python
@router.patch("/settings", response_model=SettingsResponse)
def update_settings(update: SettingsUpdate) -> SettingsResponse:
    stored = settings_store.update(update.workspace_storage_location)
    return _build_response(stored)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && uv run pytest tests/test_settings.py -v`
Expected: PASS (6 tests total).

- [ ] **Step 5: Run the full backend suite + linters**

Run: `cd apps/api && uv run pytest && uv run ruff check . && uv run mypy src`
Expected: all green (existing tests + new ones pass; ruff and mypy clean).

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/vibing_api/api/routes/settings.py apps/api/tests/test_settings.py
git commit -m "feat(api): add PATCH /settings endpoint"
```

---

## Task 5: Persist the settings file on the data volume

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Add the env var**

In `Dockerfile`, add a line next to the existing `ENV VIBING_STATIC_DIR=/app/dist` (in the `final` stage, before `EXPOSE 8080`):

```dockerfile
ENV VIBING_SETTINGS_FILE=/data/settings.json
```

The surrounding env block should read:

```dockerfile
ENV VIBING_DATABASE_URL=sqlite:////data/vibing.db
ENV VIBING_STATIC_DIR=/app/dist
ENV VIBING_SETTINGS_FILE=/data/settings.json
ENV PYTHONUNBUFFERED=1
```

- [ ] **Step 2: Verify the Dockerfile parses**

Run: `docker build -t vibing-vib10-check . >/dev/null && echo OK`
Expected: prints `OK` (build succeeds). If Docker is unavailable in this environment, instead confirm by inspection that the new `ENV` line sits in the `final` stage alongside the other `VIBING_*` vars; note in the commit that the build was not run.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore(docker): persist settings file on data volume"
```

---

## Task 6: Frontend settings API client

**Files:**
- Modify: `apps/web/src/lib/api.ts`

- [ ] **Step 1: Add the `sendJson` helper**

In `apps/web/src/lib/api.ts`, immediately after the existing `getJson` function, add:

```ts
async function sendJson<T>(path: string, method: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`${path} ${res.status}`)
  }
  return (await res.json()) as T
}
```

- [ ] **Step 2: Add the settings types and fetchers**

Append to the end of `apps/web/src/lib/api.ts`:

```ts
export interface RuntimeDetection {
  docker: boolean | null
  podman: boolean | null
  devcontainer_cli: boolean | null
  claude_code: boolean | null
}

export interface SettingsResponse {
  workspace_storage_location: string
  backend_host: string
  backend_port: number
  editor_preference: string | null
  notifications_enabled: boolean | null
  runtime: RuntimeDetection
}

export function fetchSettings(): Promise<SettingsResponse> {
  return getJson<SettingsResponse>('/api/v1/settings')
}

export function updateSettings(patch: {
  workspace_storage_location: string
}): Promise<SettingsResponse> {
  return sendJson<SettingsResponse>('/api/v1/settings', 'PATCH', patch)
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd apps/web && pnpm build`
Expected: build succeeds, no TypeScript errors. (`sendJson` is referenced by `updateSettings`, so it is not flagged as unused.)

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): add settings API client"
```

---

## Task 7: Build the settings page

**Files:**
- Modify: `apps/web/src/routes/Settings.tsx`

- [ ] **Step 1: Rewrite the component**

Replace the entire contents of `apps/web/src/routes/Settings.tsx` with:

```tsx
import { useEffect, useState, type ReactNode } from 'react'
import { PageHeader } from '../components/PageHeader'
import { fetchSettings, updateSettings, type SettingsResponse } from '../lib/api'
import { cn } from '../lib/cn'

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; settings: SettingsResponse }
  | { kind: 'error' }

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const RUNTIME_ROWS: [keyof SettingsResponse['runtime'], string][] = [
  ['docker', 'Docker'],
  ['podman', 'Podman'],
  ['devcontainer_cli', 'Dev Container CLI'],
  ['claude_code', 'Claude Code'],
]

const inputClass =
  'rounded-md border border-border bg-bg px-3 py-1.5 text-[13px] text-text outline-none focus:border-accent'
const readOnlyClass =
  'rounded-md border border-border bg-surface-muted px-3 py-1.5 text-[13px] text-text-muted'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-border px-6 py-5">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[13px] font-medium text-text">{label}</label>
      {children}
      {hint && <p className="text-xs text-text-muted">{hint}</p>}
    </div>
  )
}

function runtimeLabel(value: boolean | null): string {
  if (value === null) return 'Not detected yet'
  return value ? 'Available' : 'Not found'
}

export function Settings() {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [storageLocation, setStorageLocation] = useState('')
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        setState({ kind: 'ready', settings })
        setStorageLocation(settings.workspace_storage_location)
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (state.kind === 'loading') {
    return (
      <>
        <PageHeader title="Settings" />
        <div className="flex h-full items-center justify-center p-8 text-[13px] text-text-muted">
          Loading settings…
        </div>
      </>
    )
  }

  if (state.kind === 'error') {
    return (
      <>
        <PageHeader title="Settings" />
        <div className="flex h-full items-center justify-center p-8">
          <div className="max-w-[320px] text-center">
            <h2 className="mb-1.5 text-[15px] font-semibold text-text">Couldn't load settings</h2>
            <p className="text-[13px] text-text-muted">
              Check that the backend is running, then reload the page.
            </p>
          </div>
        </div>
      </>
    )
  }

  const { settings } = state
  const trimmed = storageLocation.trim()
  const dirty = trimmed !== settings.workspace_storage_location
  const canSave = dirty && trimmed.length > 0 && saveStatus !== 'saving'

  function handleSave() {
    const value = storageLocation.trim()
    if (!value) return
    setSaveStatus('saving')
    updateSettings({ workspace_storage_location: value })
      .then((updated) => {
        setState({ kind: 'ready', settings: updated })
        setStorageLocation(updated.workspace_storage_location)
        setSaveStatus('saved')
      })
      .catch(() => setSaveStatus('error'))
  }

  return (
    <>
      <PageHeader title="Settings" />
      <div className="flex-1 overflow-auto">
        <Section title="Workspace">
          <Field
            label="Storage location"
            hint="Where Vibing stores workspace data on this machine."
          >
            <input
              type="text"
              value={storageLocation}
              onChange={(e) => {
                setStorageLocation(e.target.value)
                setSaveStatus('idle')
              }}
              className={cn(inputClass, 'max-w-[480px]')}
            />
          </Field>
          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={!canSave}
              className={cn(
                'rounded-md px-3 py-1.5 text-[13px] font-medium',
                canSave
                  ? 'cursor-pointer bg-accent text-white hover:opacity-90'
                  : 'cursor-not-allowed bg-surface-muted text-text-muted',
              )}
            >
              {saveStatus === 'saving' ? 'Saving…' : 'Save'}
            </button>
            {saveStatus === 'saved' && <span className="text-xs text-ok">Saved</span>}
            {saveStatus === 'error' && <span className="text-xs text-bad">Couldn't save</span>}
          </div>
        </Section>

        <Section title="Backend">
          <Field label="Host" hint="Set via environment; applies on restart.">
            <input
              type="text"
              value={settings.backend_host}
              readOnly
              className={cn(readOnlyClass, 'max-w-[480px]')}
            />
          </Field>
          <Field label="Port">
            <input
              type="text"
              value={String(settings.backend_port)}
              readOnly
              className={cn(readOnlyClass, 'max-w-[160px]')}
            />
          </Field>
        </Section>

        <Section title="Editor">
          <Field label="Preferred editor" hint="Coming soon.">
            <input
              type="text"
              value=""
              placeholder="Coming soon"
              disabled
              readOnly
              className={cn(readOnlyClass, 'max-w-[480px]')}
            />
          </Field>
        </Section>

        <Section title="Notifications">
          <Field label="Notifications" hint="Coming soon.">
            <label className="inline-flex cursor-not-allowed items-center gap-2">
              <input type="checkbox" disabled className="h-4 w-4 cursor-not-allowed" />
              <span className="text-[13px] text-text-muted">Coming soon</span>
            </label>
          </Field>
        </Section>

        <Section title="Runtime detection">
          <div className="space-y-2">
            {RUNTIME_ROWS.map(([key, label]) => (
              <div key={key} className="flex max-w-[480px] items-center justify-between">
                <span className="text-[13px] text-text">{label}</span>
                <span className="text-xs text-text-muted">{runtimeLabel(settings.runtime[key])}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd apps/web && pnpm build`
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 3: Manual browser check**

Start the backend and frontend (per the project's run skill / `scripts/start.sh`, or run the API with `uv run uvicorn vibing_api.main:app` and the web app with `pnpm dev`). Then confirm at `/settings`:
- Storage location shows a default path (`<settings-file-dir>/workspaces`) when nothing is saved.
- Editing the path enables **Save**; clicking it shows "Saved"; the value survives a page reload.
- Host shows `0.0.0.0`, Port shows `8080`, both read-only.
- Editor and Notifications render disabled with "Coming soon".
- Runtime detection lists Docker / Podman / Dev Container CLI / Claude Code, each "Not detected yet".
- With the backend stopped, the page shows "Couldn't load settings".

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/routes/Settings.tsx
git commit -m "feat(web): build settings page"
```

---

## Final verification

- [ ] `cd apps/api && uv run pytest` — all backend tests pass.
- [ ] `cd apps/api && uv run ruff check . && uv run mypy src` — clean.
- [ ] `cd apps/web && pnpm build` — TypeScript clean.
- [ ] Manual `/settings` checks above all pass.
- [ ] All acceptance criteria in the spec are satisfied (settings model exists; storage location editable+persisted; host/port viewable; editor + notification placeholders viewable; runtime detection fields exist for Docker/Podman/Dev Container CLI/Claude Code).
