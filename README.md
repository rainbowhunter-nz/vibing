# vibing
Vibing is a local operations center for managing AI coding agents across isolated development workspaces

It helps developers run coding agents across multiple projects without losing track of approvals, questions, blocked sessions, or completed work.

## MVP scope

The MVP focuses on:

- local-only, single-user workflow
- workspace dashboard
- creating workspaces from local folders only (`local_path`)
- one persistent isolated workspace per project
- Claude Code support
- one active Claude Code session per workspace
- live session view and structured status
- centralized approval queue
- central inbox for questions, approvals, failures, and completions
- direct workspace editing through VS Code/native or browser editor
- basic Git status and changed-files visibility
- important event history and final session summaries

## Out of scope for MVP

The MVP does not include:

- Git URL workspace creation or repository cloning
- Codex or other coding agents
- multiple concurrent sessions in one workspace
- cloud sync or hosted execution
- multi-user collaboration
- remote worker/multi-machine orchestration
- Kubernetes
- workflow builder or plugin SDK
- full terminal log persistence

## Tech direction

- Frontend: React + Vite + TypeScript
- Backend: Python + FastAPI
- Workspace runtime agent: Python
- Local metadata: SQLite
- Workspace model: devcontainer-first, local-folder-only for MVP

## Documentation

- [MVP Product Requirement Document](https://rainbowhunter.atlassian.net/wiki/spaces/V/pages/2097153/Vibing+MVP+Product+Requirement+Document)
- [MVP Architecture](https://rainbowhunter.atlassian.net/wiki/spaces/V/pages/2293790/Vibing+MVP+Architecture)

## Status

Vibing is currently in early MVP planning and foundation implementation.

## Local development

The devcontainer ships with `uv`, `nvm` + Node LTS, `pnpm@11.3.0` (via Corepack), and Playwright already installed. Outside the devcontainer you'll need:

- Python 3.13+ and `uv >= 0.11`
- Node.js LTS (24.x) and `pnpm@11.3.0` (`corepack enable pnpm && corepack install -g pnpm@11.3.0`)

You need two terminals: one for the backend, one for the frontend.

### 1. Backend (FastAPI)

```bash
cd apps/api
uv sync
uv run uvicorn vibing_api.main:app --reload --host 127.0.0.1 --port 8000
```

The backend listens on `http://localhost:8000`. The SQLite database is initialized automatically on startup as `vibing.db` in the working directory (override with the `VIBING_DATABASE_URL` env var, e.g. `sqlite:////tmp/vibing.db`).

Direct health check:

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

The dev server listens on `http://localhost:5173` and proxies `/api/v1/*` to `http://localhost:8000` (see `apps/web/vite.config.ts`). Application code should call the backend via the relative `/api/v1/...` path — do not hardcode `http://localhost:8000`.

Open `http://localhost:5173`; the page should show "Connected to `vibing-api`" once both servers are running.

### Lockfiles

Both lockfiles are committed and should be kept in sync with their manifests:

- `apps/api/uv.lock`
- `apps/web/pnpm-lock.yaml`