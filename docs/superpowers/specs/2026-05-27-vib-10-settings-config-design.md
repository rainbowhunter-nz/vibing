# VIB-10 — Settings/config foundation

## Context

Vibing is a local operations center for AI coding agents: a React + Vite + TypeScript frontend backed by a FastAPI + SQLite service. VIB-8 shipped the app shell and five route placeholders; VIB-9 turned `/workspaces` into a live, data-driven list. The `/settings` route still renders only an `<EmptyState>` ("Settings coming soon", `apps/web/src/routes/Settings.tsx`).

The backend already has an env-driven `Settings` class (`apps/api/src/vibing_api/core/config.py`, built on `pydantic-settings`) that holds **process/env config**: `app_name`, `api_v1_prefix`, `database_url`, `static_dir`. A read-only `GET /api/v1/config` exposes a safe subset.

VIB-10 introduces a separate, user-facing **settings** concept so Vibing can be configured for the user's machine. This is a *foundation* ticket: it establishes the model, persistence, API, and the settings page, with most fields intentionally read-only or placeholder for now.

## Goal

Stand up a persisted, editable user-settings foundation: a settings model, a JSON-file persistence layer, `GET`/`PATCH` endpoints, and a real settings page — sized strictly to the acceptance criteria. Exactly one field is genuinely editable and saved this ticket (workspace storage location); everything else is read-only or an honest placeholder.

## Acceptance criteria (from VIB-10)

- Settings model exists.
- User can view or configure workspace storage location.
- User can view or configure backend host/port setting.
- User can view or configure editor preference placeholder.
- User can view notification preference placeholder.
- Runtime detection fields exist for Docker, Podman, Dev Container CLI, and Claude Code, even if detection is implemented later.

### How each criterion is met

| Criterion | Treatment this ticket |
|---|---|
| Settings model exists | `SettingsResponse` Pydantic model + `StoredSettings` (persisted shape) |
| Workspace storage location | **Editable + persisted** to a JSON file via `PATCH` |
| Backend host/port | **View** only — sourced from env config, read-only (changing at runtime is meaningless without a restart) |
| Editor preference | **Placeholder** — present in the model, always `null`, rendered as a disabled input |
| Notification preference | **Placeholder** — present in the model, always `null`, rendered as a disabled toggle |
| Runtime detection fields | Four fields (`docker`, `podman`, `devcontainer_cli`, `claude_code`) exist in the response, all `null`; a `detect_runtimes()` stub is the seam for later |

## Approach

Add user settings as a concept **distinct from** the existing env `Settings` class. Persist the one editable preference to a **JSON file on disk** (not SQLite — a deliberate choice for this machine-local config). The `GET` response is assembled from four sources:

1. **JSON file** — editable preferences (`workspace_storage_location`).
2. **Env config** — `backend_host` / `backend_port`, read-only.
3. **Placeholder defaults** — `editor_preference`, `notifications_enabled` (always `null`).
4. **Runtime detection** — `detect_runtimes()` stub returning all-`null`.

The frontend rewrites `Settings.tsx` into a real, sectioned page following the established typed-fetch + discriminated-union-state pattern (VIB-9). No new dependencies; no new frontend component files.

### Naming (avoiding collision with the existing `Settings`)

- `Settings` / `settings` (existing, `core/config.py`) → **process/env config**. Unchanged in purpose; gains three new env fields (`backend_host`, `backend_port`, `settings_file`).
- New module `core/settings_store.py` → **user preferences** persistence (`StoredSettings`, `load`, `update`).
- New route `api/routes/settings.py` → `SettingsResponse`, `SettingsUpdate`, the `/settings` endpoints.

## Persistence (JSON file)

New module `apps/api/src/vibing_api/core/settings_store.py`.

- **File path** comes from a new env setting `VIBING_SETTINGS_FILE` (`Settings.settings_file`), default `~/.vibing/settings.json` for local dev. The Dockerfile overrides it to `/data/settings.json` so settings persist on the data volume, exactly like the DB.
- `load() -> StoredSettings` — reads and parses the JSON file. If the file is missing, returns defaults (no error). Unknown keys in the file are ignored.
- `update(patch: SettingsUpdate) -> StoredSettings` — merges the patch into current values and writes **atomically** (write to a temp file in the same dir, then `os.replace`). Creates the parent directory with `mkdir(parents=True, exist_ok=True)` first.
- `StoredSettings` holds only the editable field this ticket: `workspace_storage_location: str`.
- **Default storage location** is derived from the settings-file's parent directory → `<settings_file_dir>/workspaces`. So the container (`/data/settings.json`) defaults to `/data/workspaces`, and local dev (`~/.vibing/settings.json`) defaults to `~/.vibing/workspaces`. This default is what `GET` returns until the user saves a value.

## API contract

New route module `apps/api/src/vibing_api/api/routes/settings.py`, registered in `main.py` alongside the other routers (same `api_v1_prefix`).

### `GET /api/v1/settings` → `SettingsResponse`

```json
{
  "workspace_storage_location": "/data/workspaces",
  "backend_host": "0.0.0.0",
  "backend_port": 8080,
  "editor_preference": null,
  "notifications_enabled": null,
  "runtime": {
    "docker": null,
    "podman": null,
    "devcontainer_cli": null,
    "claude_code": null
  }
}
```

Field sources and types:

| Field | Type | Source | Editable? |
|---|---|---|---|
| `workspace_storage_location` | `str` | JSON file (or derived default) | Yes (PATCH) |
| `backend_host` | `str` | env `Settings` (default `0.0.0.0`) | No (read-only) |
| `backend_port` | `int` | env `Settings` (default `8080`) | No (read-only) |
| `editor_preference` | `str \| None` | constant `null` | No (placeholder) |
| `notifications_enabled` | `bool \| None` | constant `null` | No (placeholder) |
| `runtime.docker` | `bool \| None` | `detect_runtimes()` stub → `null` | No (later) |
| `runtime.podman` | `bool \| None` | `detect_runtimes()` stub → `null` | No (later) |
| `runtime.devcontainer_cli` | `bool \| None` | `detect_runtimes()` stub → `null` | No (later) |
| `runtime.claude_code` | `bool \| None` | `detect_runtimes()` stub → `null` | No (later) |

`runtime` is a nested `RuntimeDetection` model. `null` for a runtime field means "not detected yet" (detection is a later ticket).

### `PATCH /api/v1/settings` → `SettingsResponse`

Request body `SettingsUpdate`:

```json
{ "workspace_storage_location": "/Users/me/vibing/workspaces" }
```

- Only `workspace_storage_location` is accepted. The field is required in the patch body for this ticket (the single editable setting); it must be a non-empty string (whitespace-only rejected). Validation failure returns the standard error envelope.
- No other fields are writable. Per Pydantic model definition, unexpected fields are rejected (`extra="forbid"`) so a client cannot attempt to set host/port/placeholders.
- On success: persists via `settings_store.update`, returns the full reassembled `SettingsResponse`.

### `backend_host` / `backend_port` added to env `Settings`

`core/config.py` gains:

```python
backend_host: str = "0.0.0.0"
backend_port: int = 8080
settings_file: str = str(Path.home() / ".vibing" / "settings.json")
```

Defaults match the Dockerfile's uvicorn launch command (`--host 0.0.0.0 --port 8080`) so the displayed values are accurate. Wiring uvicorn to actually read these (instead of the hardcoded CMD args) is **out of scope** — this ticket only surfaces the configured values.

## Frontend — `Settings.tsx`

Rewrite the placeholder route into a real page. Everything lands in two files: additions to `lib/api.ts` and the `Settings.tsx` rewrite (no new component files — matches VIB-9).

### `lib/api.ts` additions

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

// new helper — getJson is GET-only
async function sendJson<T>(path: string, method: string, body: unknown): Promise<T> { ... }

export function fetchSettings(): Promise<SettingsResponse> {
  return getJson<SettingsResponse>('/api/v1/settings')
}

export function updateSettings(
  patch: { workspace_storage_location: string },
): Promise<SettingsResponse> {
  return sendJson<SettingsResponse>('/api/v1/settings', 'PATCH', patch)
}
```

### Page structure

State machine `{ kind: 'loading' } | { kind: 'ready'; settings: SettingsResponse } | { kind: 'error' }`, loaded on mount with the `cancelled` guard (same pattern as `Workspaces`/`RailBackend`). The editable field has local input state plus a save status (`idle | saving | saved | error`).

| Section | Field(s) | Treatment |
|---|---|---|
| **Workspace** | storage location | Editable text input + **Save** button → `PATCH`. Inline feedback: saving / saved / error. Save disabled while unchanged or empty. |
| **Backend** | host, port | Read-only display, muted, with note: "Set via environment; applies on restart." |
| **Editor** | preference | Disabled input/select, muted, "Coming soon." |
| **Notifications** | enabled | Disabled toggle, muted, "Coming soon." |
| **Runtime detection** | Docker, Podman, Dev Container CLI, Claude Code | Read-only rows; each shows "Not detected yet" (value is `null`). |

### Loading & error states

- `loading` — centered muted "Loading settings…" line (matches `Workspaces`).
- `error` — centered "Couldn't load settings." with a muted sub-line ("Check that the backend is running, then reload."). No retry button (consistent with VIB-9; reload is recovery).
- `ready` — the sectioned form.

Styling: Tailwind v4 with the existing `@theme` tokens (`text-text-muted`, `bg-surface-muted`, `border-border`, `text-accent`, etc.), reuse `PageHeader` and `cn()`. No new dependencies.

## Dockerfile

Add one line so user settings persist on the `/data` volume alongside the DB (without it, `~/.vibing/settings.json` lives on the container's ephemeral filesystem and is lost on `docker rm`/`run`):

```dockerfile
ENV VIBING_SETTINGS_FILE=/data/settings.json
```

## Tests

`apps/api/tests/test_settings.py` (pytest), with a `settings_file` fixture that points `Settings.settings_file` at `tmp_path` via `monkeypatch` (mirrors the existing `db_path` fixture in `conftest.py`).

- `GET` returns defaults when no settings file exists (storage location is the derived `<dir>/workspaces` default).
- `PATCH` persists `workspace_storage_location`; a subsequent `GET` returns the new value.
- Persistence survives a fresh `TestClient` (simulated restart) given the same settings file.
- `PATCH` with an empty/whitespace value is rejected (standard error envelope).
- `PATCH` rejects fields other than `workspace_storage_location` (`extra="forbid"`).
- `backend_host` / `backend_port` reflect env config; overriding the env vars changes the response.
- `runtime.*` fields are all present and `null`; `editor_preference` and `notifications_enabled` are `null`.

Frontend: the project has no test runner today. Verification is `pnpm build` (TypeScript clean) + a manual browser check, per VIB-9.

## Out of scope

- Actual runtime detection logic for Docker/Podman/Dev Container CLI/Claude Code (fields exist and return `null`; `detect_runtimes()` is a stub).
- Wiring any behavior to `editor_preference` or `notifications_enabled` (placeholders only).
- Making `backend_host`/`backend_port` editable, or wiring uvicorn to read them instead of the Dockerfile CMD args.
- Consuming `workspace_storage_location` anywhere (no consumer exists yet; it persists a preference for future use).
- Migrating or restructuring the existing env `Settings` class beyond the three added fields.
- Auth, multiple settings profiles, import/export, or a settings-changed event.
- A frontend test runner.

## Risks and watchouts

- **Container persistence.** The default `~/.vibing/settings.json` is *not* on the persistent volume; the Dockerfile `ENV VIBING_SETTINGS_FILE=/data/settings.json` is what makes settings durable in deployment. Both must land together.
- **Naming confusion.** Two "settings" exist: env `Settings` (process config) and user settings (`settings_store` / `SettingsResponse`). The module/model names keep them distinct; reviewers should not conflate them.
- **Concurrent writes / partial files.** The atomic write (temp file + `os.replace`) prevents a torn settings file if a write is interrupted.
- **Displayed host/port may diverge from reality** if someone changes the uvicorn CMD without updating env defaults. Defaults are chosen to match the current Dockerfile; noted as a known limitation since wiring uvicorn is out of scope.
- **Strict-mode double mount** fires the fetch twice in dev; the `cancelled` guard makes it harmless (same as VIB-9).
- **`extra="forbid"` on `SettingsUpdate`** is what enforces "only the editable field is writable" — important so the endpoint can't be used to set read-only/placeholder fields.

## Done-when checklist

- `uv run pytest` passes, including the new `test_settings.py`.
- `pnpm build` succeeds (TypeScript clean).
- With the backend running and no settings file, `GET /api/v1/settings` returns the assembled defaults; `/settings` page shows the storage location default, read-only host/port, disabled editor/notification placeholders, and four "Not detected yet" runtime rows.
- Editing the storage location and clicking **Save** issues a `PATCH`, shows "saved", and the value survives a page reload and a backend restart.
- `PATCH` with an empty value or an extra field is rejected.
- With the backend stopped, `/settings` shows the "Couldn't load settings." error state.
- The Dockerfile sets `VIBING_SETTINGS_FILE=/data/settings.json`.
