# vibing

Vibing is a local control panel for running coding harnesses across isolated devcontainers.

It helps developers run Claude Code and other coding harnesses across multiple local projects
without losing track of running containers, harness status, or delegated work.

## What Runs

- **Frontend:** React + Vite app in `apps/web`.
- **Control Plane:** FastAPI + SQLite backend in the root Python package. Drives the Devcontainer
  lifecycle directly in-process (no separate host worker).
- **Devcontainer Runtime:** `vibing runtime devcontainer`, runs inside a devcontainer. Manages
  harness credentials, reports Harness Status, and hosts the MCP delegation server.

For deeper architecture, domain language, and ADRs, see [`docs/overview.md`](docs/overview.md).

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
uv run uvicorn vibing_api.main:app --reload --host 127.0.0.1 --port 8080
```

Backend: `http://localhost:8080`

Health check:

```bash
curl http://localhost:8080/api/v1/health
```

### 2. Frontend

```bash
cd apps/web
pnpm install
pnpm dev
```

Frontend: `http://localhost:5173`

The Vite dev server proxies `/api/v1/*` to `http://localhost:8080`.

The Control Plane drives devcontainer lifecycles directly. No additional process is needed for
lifecycle operations — start the backend and the frontend and you have the full local stack.

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

Single image (control plane + frontend baked in):

```bash
scripts/build-image.sh   # builds the `vibing` image
```

Quick preview of the built image (UI/API only — no host Docker socket, so devcontainer
lifecycle is disabled):

```bash
./scripts/start.sh
./scripts/start.sh --stop
```

For full docker-out-of-docker deployment, run the pre-built image via compose
(`scripts/build-image.sh` then `docker compose up`) — see
[`docs/deployment.md`](docs/deployment.md).

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
uv run vibing runtime devcontainer --help
uv run vibing harness --help
uv run vibing system --help
```

## Configuration

Backend settings use the `VIBING_` prefix and may be set in the shell or root `.env` file.

Common settings:

- `VIBING_DATABASE_URL`: default `sqlite:///./vibing.db`
- `VIBING_STATIC_DIR`: built frontend directory for single-container serving
- `VIBING_API_V1_PREFIX`: default `/api/v1`

See [`docs/overview.md`](docs/overview.md) for more context.
