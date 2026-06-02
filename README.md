# vibing

Vibing is a local operations center for managing AI coding agents across isolated devcontainers.

It helps developers run Claude Code across multiple local projects without losing track of running containers, agent sessions, approvals, questions, blocked work, or completed work.

## What Runs

- **Frontend:** React + Vite app in `apps/web`.
- **Control Plane:** FastAPI + SQLite backend in the root Python package.
- **Host Runtime Worker:** `vibing host-runtime`, runs on the host and controls the Dev Container CLI.
- **Devcontainer Runtime Agent:** `vibing devcontainer-runtime`, runs inside a devcontainer and controls Claude Code.

For deeper architecture, domain language, and MVP scope, see [`docs/overview.md`](docs/overview.md).

## Prerequisites

Inside the devcontainer these are already available. Outside it, install:

- Python 3.13+
- `uv >= 0.11`
- Node.js LTS 24.x
- `pnpm@11.3.0`
- Dev Container CLI (`devcontainer`) if you want runtime lifecycle operations

Install pnpm with Corepack:

```bash
corepack enable pnpm
corepack install -g pnpm@11.3.0
```

## Run Locally

Use separate terminals.

### 1. Backend

```bash
uv sync
uv run uvicorn vibing_api.main:app --reload --host 127.0.0.1 --port 8000
```

Backend: `http://localhost:8000`

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

### 2. Frontend

```bash
cd apps/web
pnpm install
pnpm dev
```

Frontend: `http://localhost:5173`

The Vite dev server proxies `/api/v1/*` to `http://localhost:8000`.

### 3. Host Runtime Worker

Start after the backend is running:

```bash
uv run vibing host-runtime
```

This connects to the Control Plane at `ws://127.0.0.1:8000/api/v1/runtime/ws` and runs devcontainer lifecycle commands through the local `devcontainer` CLI.

## Build

Python package:

```bash
uv build
```

Frontend:

```bash
cd apps/web
pnpm build
```

Production-like container preview:

```bash
./scripts/start.sh
./scripts/start.sh --stop
```

For a full single-container deployment (control plane + frontend + host-runtime)
via docker compose, see [`docs/deployment.md`](docs/deployment.md).

## Test And Check

Python:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q
uv run mypy src
```

Frontend:

```bash
cd apps/web
pnpm lint
pnpm typecheck
pnpm test
```

## Useful Commands

Sample data for local UI development:

```bash
uv run vibing dev sample_data seed
uv run vibing dev sample_data status
uv run vibing dev sample_data reset
```

Runtime help:

```bash
uv run vibing --help
uv run vibing host-runtime --help
uv run vibing devcontainer-runtime --help
```

## Configuration

Backend settings use the `VIBING_` prefix and may be set in the shell or root `.env` file.

Common settings:

- `VIBING_DATABASE_URL`: default `sqlite:///./vibing.db`
- `VIBING_STATIC_DIR`: built frontend directory for single-container serving
- `VIBING_API_V1_PREFIX`: default `/api/v1`

See [`docs/overview.md`](docs/overview.md) for more context.
