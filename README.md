# vibing

Vibing is a local operations center for managing AI coding agents across isolated devcontainers.

It helps developers run a coding agent across multiple projects without losing track of approvals, questions, blocked sessions, or completed work. The agent is Claude Code today; the product treats "agent" as a role, not a hard-wired vendor.

## Domain language & decisions

This repo keeps its canonical language and architectural decisions in version control. Read these before contributing — code, docs, and PRs should use the same terms:

- [`CONTEXT.md`](CONTEXT.md) — the glossary. Canonical entities: **Devcontainer**, **Agent Session**, **Control Plane**, **Runtime**, **Command**, **Runtime Event**, **Inbox Event**, **Session Output**, etc.
- [`docs/adr/`](docs/adr/) — Architecture Decision Records (see [the ADR index](docs/adr/CLAUDE.md)).

The three load-bearing decisions:

- **[ADR-0001](docs/adr/0001-devcontainer-source-is-a-single-local-path.md)** — a Devcontainer's source is a single `local_path` column, not a generic `source_type`/`source_value` descriptor.
- **[ADR-0002](docs/adr/0002-inbox-is-a-projection-of-the-runtime-event-stream.md)** — `runtime_events` is the single append-only source of truth; all read-model state (inbox, statuses, approvals, summaries) is a projection of it, written only by the Control Plane.
- **[ADR-0003](docs/adr/0003-runtimes-connect-to-the-control-plane-over-tcp-ip-in-a-star-topology.md)** — runtimes connect to the Control Plane over TCP/IP in a star topology; runtimes never talk to each other.

## Core concepts

- **Devcontainer** — the central persistent entity: one isolated container bound to one local folder (`local_path`). It owns its agent-sessions, approvals, inbox, and history, and exists even when stopped.
- **Agent Session** — one run of a coding agent inside a *running* Devcontainer; at most one active per Devcontainer (MVP).
- **Control Plane** — the backend (FastAPI + SQLite). The single hub: it sends Commands to runtimes and projects the Runtime Events they emit into all read-model state. The frontend is a separate client over `/api/v1`, not part of the Control Plane.
- **Runtimes** — the **Host Runtime Worker** (owns the Devcontainer lifecycle, on the host) and the **Devcontainer Runtime Agent** (owns the Agent Session lifecycle, inside the container).

Two distinct lifecycles, with deliberately distinct verbs:

- **Devcontainer:** `created → starting → running → stopping → stopped` (+ `error`). *Stopping the devcontainer ends any active agent-session inside it.*
- **Agent Session:** `starting → running ⇄ waiting_for_approval → completed / failed / stopped`. *Stopping the agent-session leaves the devcontainer running.*

## MVP scope

- local-only, single-user workflow
- devcontainer dashboard
- devcontainers created from local folders only (single `local_path` field)
- one persistent isolated devcontainer per project
- Claude Code support; one active agent-session per devcontainer
- live session view (Session Output) and structured agent-session status
- centralized approval queue (`pending → approved | rejected`)
- inbox for questions, approvals, failures, completions
- direct editing via VS Code / native / browser editor
- basic Git status and changed-files view
- important event history and final session summaries

## Non-goals (MVP)

- Git URL creation or repo cloning
- Codex or other coding agents
- multiple concurrent agent-sessions per devcontainer
- cloud sync, hosted execution, remote workers
- multi-user collaboration
- Kubernetes
- workflow builder or plugin SDK
- Session Output / terminal scrollback persistence

## Local-first assumptions

- runs entirely on the developer's machine
- no auth, no remote user accounts
- single user, single host
- SQLite file in the working directory holds all metadata, with `runtime_events` as the source of truth
- backend on `127.0.0.1`, frontend on `127.0.0.1`, no public exposure
- devcontainers are local folder paths owned by the developer

## Tech stack

- Frontend: React + Vite + TypeScript + Tailwind
- Backend (Control Plane): Python 3.13 + FastAPI
- Runtimes: Python (Host Runtime Worker, Devcontainer Runtime Agent)
- Local metadata: SQLite
- Devcontainer model: devcontainer-first, local-folder-only for MVP

## Documentation

- [MVP Product Requirement Document](https://rainbowhunter.atlassian.net/wiki/spaces/V/pages/2097153/Vibing+MVP+Product+Requirement+Document)
- [MVP Architecture](https://rainbowhunter.atlassian.net/wiki/spaces/V/pages/2293790/Vibing+MVP+Architecture)
- [`CONTEXT.md`](CONTEXT.md) and [`docs/adr/`](docs/adr/) (authoritative for terminology and decisions)

## Status

Early MVP — foundation implemented; core decisions landed.

- Workspace→Devcontainer rename is complete: table `devcontainers`, `/api/v1/devcontainers` routes, `devcontainer_id` FKs throughout.
- Schema simplified to a single `local_path` column (ADR-0001); the `"deleted"` status is gone; status/event vocabularies are typed `Literal`s.
- Persistence is behind per-entity repository modules; route handlers contain no SQL.
- Read-model state (devcontainer/agent-session status, inbox, approvals, summaries) is produced by a single projection reducer over the `runtime_events` stream (ADR-0002) — the sole writer of derived state.
- **Still pending:** the runtime transport / TCP-IP channel between Control Plane and runtimes is not yet implemented (ADR-0003 — the `handle()` skeletons are placeholders), and Session Output (live terminal stream) is deferred.

## Local development

### Prerequisites

The devcontainer ships with `uv`, `nvm` + Node LTS, `pnpm@11.3.0` (via Corepack), and Playwright. Outside the devcontainer install:

- Python 3.13+ and `uv >= 0.11`
- Node.js LTS (24.x)
- `pnpm@11.3.0` — `corepack enable pnpm && corepack install -g pnpm@11.3.0`

You need two terminals: one for backend, one for frontend.

### 1. Backend (FastAPI Control Plane)

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

Every sample row's `id` is prefixed with `sample-` and every sample name starts with `[sample]`. Real rows created via the API are never touched by `reset`.

### Production-like preview (single container)

```bash
./scripts/start.sh           # builds image, starts container on :8080
./scripts/start.sh --stop    # stops the container
```

Serves the built frontend and API from one container. DB lives in the `vibing-data` docker volume at `/data/vibing.db`.

### Checks before review

Run these before opening a PR. CI (`.github/workflows/ci.yml`) runs the same set on every push to `main` and pull request; none of them require the devcontainer/host runtime.

**Backend** — run per Python project (`apps/api`, `packages/protocol`, `packages/host_runtime`, `packages/devcontainer_runtime`); `uv run` syncs deps on first use:

```bash
cd apps/api            # or any packages/* dir
uv run ruff check .            # lint
uv run ruff format --check .   # format (drop --check to apply)
uv run pytest -q               # tests (protocol has none)
uv run mypy src                # type-check (apps/api only)
```

**Frontend** (`apps/web`):

```bash
cd apps/web
pnpm lint        # eslint
pnpm typecheck   # tsc -b
pnpm test        # vitest
```

### Lockfiles

Both lockfiles are committed and must stay in sync with their manifests:

- `apps/api/uv.lock`
- `apps/web/pnpm-lock.yaml`
