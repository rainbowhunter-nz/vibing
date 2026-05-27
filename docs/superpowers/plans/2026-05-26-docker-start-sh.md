# Docker Single-Container Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the Vibing app (React frontend + FastAPI backend) into a single Docker image and provide `scripts/start.sh` to build and run it.

**Architecture:** A multi-stage Dockerfile builds the React frontend with pnpm, then assembles a Python 3.13-slim image that runs uvicorn on port 8080. FastAPI serves the API at `/api/v1/` and the built static files at `/` via a conditional `StaticFiles` mount (only active when `VIBING_STATIC_DIR` is set, so dev mode is unchanged). SQLite data is persisted via a named Docker volume mounted at `/data`.

**Tech Stack:** Python 3.13, uv, FastAPI `StaticFiles`, uvicorn, Node 24, pnpm 11.3.0, Docker multi-stage build

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `apps/api/src/vibing_api/core/config.py` | Add optional `static_dir` setting |
| Modify | `apps/api/src/vibing_api/main.py` | Mount `StaticFiles` when `static_dir` is set |
| Create | `apps/api/tests/test_static_serving.py` | Tests for static file serving behaviour |
| Create | `.dockerignore` | Keep build context lean |
| Create | `Dockerfile` | Multi-stage build at repo root |
| Modify | `scripts/start.sh` | Build image and run container |

---

### Task 1: Add `static_dir` setting

**Files:**
- Modify: `apps/api/src/vibing_api/core/config.py`
- Create: `apps/api/tests/test_static_serving.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_static_serving.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.main import create_app


def test_static_dir_defaults_to_none() -> None:
    assert settings.static_dir is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/api && uv run pytest tests/test_static_serving.py -v
```

Expected: FAIL — `Settings` has no attribute `static_dir`.

- [ ] **Step 3: Add `static_dir` to `Settings`**

Edit `apps/api/src/vibing_api/core/config.py` — add one field:

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


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd apps/api && uv run pytest tests/test_static_serving.py -v
```

Expected: PASS.

- [ ] **Step 5: Verify existing tests still pass**

```bash
cd apps/api && uv run pytest -v
```

Expected: all existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/vibing_api/core/config.py apps/api/tests/test_static_serving.py
git commit -m "feat: add optional static_dir setting to Settings"
```

---

### Task 2: Mount StaticFiles in `create_app()`

**Files:**
- Modify: `apps/api/src/vibing_api/main.py`
- Modify: `apps/api/tests/test_static_serving.py`

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_static_serving.py`:

```python
def test_static_files_served_when_static_dir_configured(
    tmp_path: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>vibing</h1>")
    monkeypatch.setattr(settings, "static_dir", str(static_dir))
    with TestClient(create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert b"vibing" in response.content


def test_api_routes_take_precedence_over_static(
    tmp_path: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>vibing</h1>")
    monkeypatch.setattr(settings, "static_dir", str(static_dir))
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_no_static_mount_when_static_dir_is_none(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "static_dir", None)
    with TestClient(create_app()) as client:
        response = client.get("/some-nonexistent-path")
    assert response.status_code == 404
    # Must be FastAPI's JSON 404, not a static file mount 404
    assert response.headers["content-type"].startswith("application/json")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/api && uv run pytest tests/test_static_serving.py -v
```

Expected: `test_static_files_served_when_static_dir_configured` and `test_api_routes_take_precedence_over_static` FAIL (no static mount yet); `test_static_dir_defaults_to_none` PASS.

- [ ] **Step 3: Add the StaticFiles mount to `create_app()`**

Replace `apps/api/src/vibing_api/main.py` with:

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vibing_api.api.routes import config, health, status, workspaces
from vibing_api.core.config import settings
from vibing_api.core.database import init_db
from vibing_api.core.errors import register_error_handlers


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_error_handlers(app)
    for router in (health.router, status.router, config.router, workspaces.router):
        app.include_router(router, prefix=settings.api_v1_prefix)
    if settings.static_dir:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps/api && uv run pytest tests/test_static_serving.py -v
```

Expected: all 4 tests in `test_static_serving.py` PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd apps/api && uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/vibing_api/main.py apps/api/tests/test_static_serving.py
git commit -m "feat: mount StaticFiles when VIBING_STATIC_DIR is set"
```

---

### Task 3: Create `.dockerignore`

**Files:**
- Create: `.dockerignore` (repo root)

- [ ] **Step 1: Create `.dockerignore`**

Create `/workspaces/vibing/.dockerignore`:

```
# Python
**/__pycache__/
**/*.py[cod]
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/.venv/
**/venv/

# Node
**/node_modules/
**/dist/
**/.pnpm-store/

# Database
*.db
*.sqlite
*.sqlite3

# Dev tooling
.devcontainer/
.claude/
.superpowers/
docs/

# Git
.git/

# Env / secrets
.env
.env.*
```

- [ ] **Step 2: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore for lean build context"
```

---

### Task 4: Write the Dockerfile

**Files:**
- Create: `Dockerfile` (repo root)

- [ ] **Step 1: Create `Dockerfile`**

Create `/workspaces/vibing/Dockerfile`:

```dockerfile
# Stage 1: build frontend
FROM node:24-slim AS builder
WORKDIR /build
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN corepack install -g pnpm@11.3.0 && pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

# Stage 2: run backend + serve built frontend
FROM python:3.13-slim AS final
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Install Python dependencies (separate layer for cache efficiency)
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project

# Copy source and complete install
COPY apps/api/src ./src
RUN uv sync --no-dev --frozen

# Copy built frontend assets
COPY --from=builder /build/dist /app/dist

ENV VIBING_DATABASE_URL=sqlite:////data/vibing.db
ENV VIBING_STATIC_DIR=/app/dist
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "vibing_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Verify the image builds**

Run from repo root (this takes a few minutes on first run):

```bash
docker build -t vibing .
```

Expected: build completes with `Successfully built` (or equivalent). Both stages complete without error.

- [ ] **Step 3: Smoke-test the image locally**

```bash
docker run --rm -p 8080:8080 -v vibing-data:/data vibing
```

In another terminal:

```bash
curl -s http://host.docker.internal:8080/api/v1/health
```

Expected: `{"status":"ok","service":"vibing-api"}`

```bash
curl -si http://host.docker.internal:8080/ | head -5
```

Expected: `HTTP/1.1 200 OK` with HTML content containing `vibing`.

Stop the test container with Ctrl-C.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "feat: add multi-stage Dockerfile for single-container deployment"
```

---

### Task 5: Write `scripts/start.sh`

**Files:**
- Modify: `scripts/start.sh`

- [ ] **Step 1: Write `scripts/start.sh`**

Replace the contents of `scripts/start.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root regardless of where this script is called from
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

IMAGE=vibing
CONTAINER=vibing
PORT=8080

echo "Building image..."
docker build -t "$IMAGE" .

echo "Starting container..."
docker rm -f "$CONTAINER" 2>/dev/null || true
docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:${PORT}" \
  -v vibing-data:/data \
  "$IMAGE"

echo "Vibing is running at http://localhost:${PORT}"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/start.sh
```

- [ ] **Step 3: Run it and verify**

```bash
./scripts/start.sh
```

Expected output:
```
Building image...
...
Starting container...
Vibing is running at http://localhost:8080
```

Then verify the container is up:

```bash
docker ps --filter name=vibing
curl -s http://host.docker.internal:8080/api/v1/health
```

Expected: container listed, health check returns `{"status":"ok","service":"vibing-api"}`.

Open `http://host.docker.internal:8080` in a browser — the React shell should load.

- [ ] **Step 4: Verify idempotency (re-run the script)**

```bash
./scripts/start.sh
```

Expected: script completes without error; old container replaced by new one; no "container name already in use" error.

- [ ] **Step 5: Commit**

```bash
git add scripts/start.sh
git commit -m "feat: add scripts/start.sh to build and run Docker container"
```

---

## Done

All tasks complete when:
- `uv run pytest` passes in `apps/api/`
- `docker build -t vibing .` succeeds
- `./scripts/start.sh` produces a running container at `http://localhost:8080`
- The React UI loads and `/api/v1/health` returns `{"status":"ok","service":"vibing-api"}`
- Re-running `./scripts/start.sh` does not error
