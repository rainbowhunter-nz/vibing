# Docker Single-Container Deployment Design

**Date:** 2026-05-26  
**Scope:** `scripts/start.sh` + `Dockerfile` at repo root + minor FastAPI static file mount

---

## Goal

Package the full Vibing app (React frontend + FastAPI backend) into a single Docker image and provide a `scripts/start.sh` that builds and runs it with one command.

## Architecture

One container, one process (uvicorn), one port (8080).

```
Browser → http://localhost:8080
              │
              ▼
         uvicorn (port 8080)
              │
         FastAPI app
         ├── /api/v1/*   → API routes (registered first, take precedence)
         └── /*          → StaticFiles mount serving apps/web/dist/
                           (html=True so React client-side routing works)
```

SQLite database is stored at `/data/vibing.db` inside the container. A named Docker volume (`vibing-data`) is mounted at `/data` to persist data across container restarts.

## Dockerfile

Multi-stage build at repo root.

### Stage 1: `builder` (node:24-slim)

- Install corepack + pnpm@11.3.0
- Copy `apps/web/`
- Run `pnpm install --frozen-lockfile && pnpm build`
- Output: `apps/web/dist/`

### Stage 2: `final` (python:3.13-slim)

- Install `uv`
- Copy `apps/api/` and sync dependencies with `uv sync --no-dev`
- Copy `apps/web/dist/` from stage 1 into `/app/dist/`
- Set `VIBING_DATABASE_URL=sqlite:////data/vibing.db` and `VIBING_STATIC_DIR=/app/dist`
- Expose port 8080
- Entrypoint: `uv run uvicorn vibing_api.main:app --host 0.0.0.0 --port 8080`

## FastAPI change

In `apps/api/src/vibing_api/main.py`, `create_app()` conditionally mounts a `StaticFiles` app:

```python
static_dir = settings.static_dir  # new optional setting, defaults to None
if static_dir:
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

`settings.static_dir` is a new optional `str | None` field in `Settings` (env var `VIBING_STATIC_DIR`). When unset (dev mode), no static mount is added and Vite handles the frontend as before.

The static mount must be added **after** all API routers so `/api/v1/` routes take precedence.

## `scripts/start.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

IMAGE=vibing
CONTAINER=vibing
VOLUME=vibing-data
PORT=8080

docker build -t "$IMAGE" .

# Remove existing container if present (idempotent re-runs)
docker rm -f "$CONTAINER" 2>/dev/null || true

docker run -d \
  --name "$CONTAINER" \
  -p "$PORT:$PORT" \
  -v "$VOLUME:/data" \
  "$IMAGE"

echo "Vibing running at http://localhost:$PORT"
```

Script is run from any directory; it resolves the repo root via `$(git rev-parse --show-toplevel)` or relative `cd` so `docker build` always uses the right context.

## Data persistence

| What | Where |
|------|-------|
| SQLite database | Named volume `vibing-data` mounted at `/data` |
| Frontend static assets | Baked into image at `/app/dist/` |

## Out of scope

- docker-compose
- nginx
- hot-reload / development mode inside Docker
- multi-user or remote deployment
- host filesystem mounts for workspace `local_path` (separate concern)
