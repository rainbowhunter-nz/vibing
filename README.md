# vibing

Vibing is a local operations center for managing AI coding agents across isolated development workspaces.

It helps developers run coding agents across multiple projects without losing track of approvals, questions, blocked sessions, or completed work.

## MVP scope

- local-only, single-user workflow
- workspace dashboard
- workspaces created from local folders only (`local_path`)
- one persistent isolated workspace per project
- Claude Code support
- one active Claude Code session per workspace
- live session view and structured status
- centralized approval queue
- inbox for questions, approvals, failures, completions
- direct workspace editing via VS Code / native / browser editor
- basic Git status and changed-files view
- important event history and final session summaries

## Non-goals (MVP)

- Git URL workspace creation or repo cloning
- Codex or other coding agents
- multiple concurrent sessions per workspace
- cloud sync, hosted execution, remote workers
- multi-user collaboration
- Kubernetes
- workflow builder or plugin SDK
- full terminal log persistence

## Local-first assumptions

- runs entirely on the developer's machine
- no auth, no remote user accounts
- single user, single host
- SQLite file in the working directory holds all metadata
- backend on `127.0.0.1`, frontend on `127.0.0.1`, no public exposure
- workspaces are local folder paths owned by the developer

## Tech stack

- Frontend: React + Vite + TypeScript + Tailwind
- Backend: Python 3.13 + FastAPI
- Workspace runtime agent: Python
- Local metadata: SQLite
- Workspace model: devcontainer-first, local-folder-only for MVP

## Documentation

- [MVP Product Requirement Document](https://rainbowhunter.atlassian.net/wiki/spaces/V/pages/2097153/Vibing+MVP+Product+Requirement+Document)
- [MVP Architecture](https://rainbowhunter.atlassian.net/wiki/spaces/V/pages/2293790/Vibing+MVP+Architecture)

## Status

Early MVP planning and foundation implementation.

## Local development

### Prerequisites

The devcontainer ships with `uv`, `nvm` + Node LTS, `pnpm@11.3.0` (via Corepack), and Playwright. Outside the devcontainer install:

- Python 3.13+ and `uv >= 0.11`
- Node.js LTS (24.x)
- `pnpm@11.3.0` — `corepack enable pnpm && corepack install -g pnpm@11.3.0`

You need two terminals: one for backend, one for frontend.

### 1. Backend (FastAPI)

```bash
cd apps/api
uv sync
uv run uvicorn vibing_api.main:app --reload --host 127.0.0.1 --port 8000
```

Backend listens on `http://localhost:8000`.

SQLite initializes automatically on startup. The DB file is created at the path in `VIBING_DATABASE_URL` (default: `vibing.db` in the working directory). The schema is applied on every start — safe to re-run.

Health check:

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","service":"vibing-api"}
```

### 2. Frontend (Vite)

```bash
cd apps/web
pnpm install
pnpm dev
```

Dev server: `http://localhost:5173`. It proxies `/api/v1/*` to `http://localhost:8000` (see `apps/web/vite.config.ts`). App code must call the backend via the relative `/api/v1/...` path — do not hardcode `http://localhost:8000`.

Open `http://localhost:5173`; the page shows "Connected to `vibing-api`" once both servers run.

### Environment variables

All backend settings use the `VIBING_` prefix. Set them in the shell or in `apps/api/.env` (auto-loaded by `pydantic-settings`).

| Variable | Default | Purpose |
| --- | --- | --- |
| `VIBING_DATABASE_URL` | `sqlite:///./vibing.db` | SQLite URL. Only `sqlite:///` is supported. |
| `VIBING_STATIC_DIR` | unset | If set, backend serves a built frontend bundle from this dir (SPA fallback). Used by the container image; leave unset in dev. |
| `VIBING_BACKEND_HOST` | `0.0.0.0` | Reported by the settings endpoint. Pass `--host` to `uvicorn` to actually bind. |
| `VIBING_BACKEND_PORT` | `8080` | Reported by the settings endpoint. Pass `--port` to `uvicorn` to actually bind. In dev use `8000` (matches the Vite proxy). |
| `VIBING_APP_NAME` | `vibing-api` | App name in OpenAPI / health responses. |
| `VIBING_API_V1_PREFIX` | `/api/v1` | Prefix for all v1 routes. |

The frontend has no env vars — it always calls `/api/v1/*` via the proxy.

### Sample data (local development only)

Populate the dashboard, inbox, and approval queue with curated sample rows for UI validation:

```bash
cd apps/api
uv run vibing dev sample_data seed
uv run vibing dev sample_data status
uv run vibing dev sample_data reset
```

Every sample row's `id` is prefixed with `sample-` and every sample workspace name starts with `[sample]`. Real rows created via the API are never touched by `reset`.

### Production-like preview (single container)

```bash
./scripts/start.sh           # builds image, starts container on :8080
./scripts/start.sh --stop    # stops the container
```

Serves the built frontend and API from one container. DB lives in the `vibing-data` docker volume at `/data/vibing.db`.

### Lockfiles

Both lockfiles are committed and must stay in sync with their manifests:

- `apps/api/uv.lock`
- `apps/web/pnpm-lock.yaml`
