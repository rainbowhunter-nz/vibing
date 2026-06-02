# Single-Image Docker-out-of-Docker Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package Control Plane + frontend + Host Runtime Worker into one image, brought up by a single `docker compose` file in a docker-out-of-docker configuration.

**Architecture:** Extend the existing two-stage `Dockerfile` final stage to also carry Node + `@devcontainers/cli` + docker CLI + git, and run both uvicorn and `vibing host-runtime` under `supervisord` (PID 1, fail-fast). A `docker-compose.yml` mounts the projects directory at an identical host path, the engine socket (user-editable for Podman), and a data volume.

**Tech Stack:** Docker multi-stage build, supervisord, docker compose, Node 24 / `@devcontainers/cli`.

This plan is packaging + docs only — **no `src/` changes**. Because there is no new application logic, tasks are verified by build/run checks rather than unit tests.

Spec: `docs/superpowers/specs/2026-06-02-docker-compose-deployment-design.md`.

---

### Task 1: supervisord config

**Files:**
- Create: `deploy/supervisord.conf`

Runs both processes; a fail-fast event listener shuts supervisord down (and thus the container) the moment either program leaves the RUNNING state. `directory=/repo` matches the existing image WORKDIR. Host-runtime flags read from env so they can be overridden.

- [ ] **Step 1: Create `deploy/supervisord.conf`**

```ini
[supervisord]
nodaemon=true
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:control-plane]
command=uv run --no-dev --frozen uvicorn vibing_api.main:app --host 0.0.0.0 --port 8080
directory=/repo
autorestart=false
startsecs=0
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0

[program:host-runtime]
command=uv run --no-dev --frozen vibing host-runtime --control-plane-url %(ENV_VIBING_CONTROL_PLANE_URL)s --agent-control-plane-url %(ENV_VIBING_AGENT_CONTROL_PLANE_URL)s
directory=/repo
autorestart=false
startsecs=0
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0

# Fail-fast: if any program exits or goes fatal, SIGTERM supervisord so the container stops.
[eventlistener:fail-fast]
command=bash -c "printf 'READY\n'; while read -r line; do kill -SIGTERM \"$PPID\"; done"
events=PROCESS_STATE_EXITED,PROCESS_STATE_FATAL,PROCESS_STATE_STOPPED
```

- [ ] **Step 2: Lint the ini for obvious typos**

Run: `python -c "import configparser; c=configparser.ConfigParser(strict=False); c.read('deploy/supervisord.conf'); print(sorted(c.sections()))"`
Expected: `['eventlistener:fail-fast', 'program:control-plane', 'program:host-runtime', 'supervisord']`

- [ ] **Step 3: Commit**

```bash
git add deploy/supervisord.conf
git commit -m "Add supervisord config for control-plane + host-runtime"
```

---

### Task 2: Extend the Dockerfile final stage

**Files:**
- Modify: `Dockerfile`

Add Node (copied from the `node:24-slim` image — same glibc base as `python:3.13-slim`), `@devcontainers/cli`, the docker CLI client (from `docker:cli`), git, and supervisor. Replace the uvicorn `CMD` with supervisord. Keep stage 1 (frontend build) and the Python install layers unchanged.

- [ ] **Step 1: Replace the final stage of `Dockerfile`**

Keep stage 1 exactly as-is. Replace everything from `# Stage 2: run backend + serve built frontend` to the end with:

```dockerfile
# Stage 2: run backend + host-runtime + serve built frontend
FROM python:3.13-slim AS final
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

# Node 24 (for the Dev Container CLI) — same glibc base, safe to copy in.
COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm

# docker CLI client — the Dev Container CLI drives the mounted daemon socket through it.
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

# git (devcontainer features), supervisor (runs both processes).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @devcontainers/cli \
    && npm cache clean --force

WORKDIR /repo

# Install Python dependencies (separate layer for cache efficiency)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# Copy source and complete install
COPY src ./src
RUN uv sync --no-dev --frozen

# Copy built frontend assets
COPY --from=builder /build/dist ./dist

# Process manager config
COPY deploy/supervisord.conf /etc/supervisor/conf.d/vibing.conf

ENV VIBING_DATABASE_URL=sqlite:////data/vibing.db
ENV VIBING_STATIC_DIR=/repo/dist
ENV VIBING_CONTROL_PLANE_URL=ws://127.0.0.1:8080/api/v1/runtime/ws
ENV VIBING_AGENT_CONTROL_PLANE_URL=ws://host.docker.internal:8080/api/v1/runtime/agent/ws
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
VOLUME /data

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/vibing.conf"]
```

- [ ] **Step 2: Verify the docker CLI source image tag exists**

Run: `docker pull docker:cli && docker pull node:24-slim`
Expected: both pull successfully (no manifest error).

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "Bundle host-runtime toolchain and supervisord into the image"
```

---

### Task 3: Build the image and smoke-test the control plane

**Files:** none (verification only).

- [ ] **Step 1: Build**

Run: `docker build --load -t vibing .`
Expected: build completes; no error on the `npm install -g @devcontainers/cli` or `COPY --from` lines.

- [ ] **Step 2: Verify the bundled tools resolve**

Run: `docker run --rm vibing bash -lc "node --version && devcontainer --version && docker --version && supervisord --version && git --version"`
Expected: a version string for each (node v24.x, a devcontainer version, a docker version, a supervisor version, a git version).

- [ ] **Step 3: Smoke-test the control plane in isolation**

Run:
```bash
docker rm -f vibing-smoke 2>/dev/null || true
docker run -d --name vibing-smoke -p 8080:8080 -v vibing-smoke-data:/data vibing
sleep 5
curl -fsS http://host.docker.internal:8080/api/v1/health
```
Expected: a healthy JSON response (e.g. `{"status":"ok"}`). The `host-runtime` program will log a connection attempt to `127.0.0.1:8080` in `docker logs vibing-smoke` — that is expected to succeed once uvicorn is up.

- [ ] **Step 4: Tear down the smoke container**

Run: `docker rm -f vibing-smoke && docker volume rm vibing-smoke-data`
Expected: removed.

- [ ] **Step 5: No commit** (verification task — nothing changed).

---

### Task 4: docker-compose.yml and .env.example

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  vibing:
    build: .
    image: vibing
    ports:
      - "8080:8080"
    volumes:
      - vibing-data:/data
      # Identical-path passthrough: host projects dir mounted at the SAME absolute
      # path inside the container so devcontainer bind-mounts resolve on the host.
      - ${PROJECTS_DIR}:${PROJECTS_DIR}
      # Container engine socket. Edit the SOURCE side for Podman — see .env.example.
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - PROJECTS_DIR=${PROJECTS_DIR}

volumes:
  vibing-data:
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Absolute host path to the directory that contains your project folders.
# Mounted at the identical path inside the container so devcontainer paths line up.
# In the UI, a devcontainer's local_path must be a path under this directory.
PROJECTS_DIR=/home/you/code

# --- Container engine socket ---------------------------------------------------
# The compose file mounts /var/run/docker.sock by default (Docker).
# For Podman, edit the SOURCE side of the socket volume in docker-compose.yml to:
#   ${XDG_RUNTIME_DIR}/podman/podman.sock:/var/run/docker.sock
# (rootless Podman) or /run/podman/podman.sock:/var/run/docker.sock (rootful).
```

- [ ] **Step 3: Validate the compose file parses**

Run: `PROJECTS_DIR=/tmp docker compose config >/dev/null && echo OK`
Expected: `OK` (no interpolation or schema error).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "Add docker compose deployment and env example"
```

---

### Task 5: Deployment doc and README pointer

**Files:**
- Create: `docs/deployment.md`
- Modify: `README.md`

- [ ] **Step 1: Create `docs/deployment.md`**

```markdown
# Deployment (single-image, docker-out-of-docker)

Vibing ships as one image running the Control Plane, frontend, and Host Runtime
Worker together. It drives the host's container engine through a mounted socket
(docker-out-of-docker), so the devcontainers it starts are siblings on the host.

## Prerequisites

- Docker (or Podman) on the host.
- A directory on the host that holds your project folders.

## Configure

Copy the example env and set your projects directory:

```bash
cp .env.example .env
# edit .env: PROJECTS_DIR=/absolute/host/path/to/your/code
```

`PROJECTS_DIR` is mounted at the **same absolute path** inside the container
(identical-path passthrough). When you create a devcontainer in the UI, its
`local_path` must be a path under `PROJECTS_DIR` — the host daemon and the
container then agree on where the files are.

### Podman

The compose file mounts `/var/run/docker.sock` by default. For Podman, edit the
source side of that volume in `docker-compose.yml` (see `.env.example` for the
exact rootless/rootful socket paths).

## Run

```bash
docker compose up --build
```

Open http://localhost:8080. Health check: `curl http://localhost:8080/api/v1/health`.

## Linux caveat: host.docker.internal in devcontainers

Started devcontainers reach the Control Plane at
`ws://host.docker.internal:8080`. On Docker Desktop (macOS/Windows) this resolves
automatically. On **Linux**, a devcontainer must add a host-gateway entry, e.g. in
its `devcontainer.json`:

```json
"runArgs": ["--add-host=host.docker.internal:host-gateway"]
```

The `devcontainer_examples/sandbox` example already includes this.

## Verify end-to-end

1. `docker compose up --build`, then open the UI.
2. Create a devcontainer whose `local_path` is a folder under `PROJECTS_DIR`.
3. Start it; confirm the container appears on the host (`docker ps`) and the
   agent-session reaches `running`.
```

- [ ] **Step 2: Add a pointer in `README.md`**

Under the `## Build` section's "Production-like container preview" area, add:

```markdown
For a full single-container deployment (control plane + frontend + host-runtime)
via docker compose, see [`docs/deployment.md`](docs/deployment.md).
```

- [ ] **Step 3: Commit**

```bash
git add docs/deployment.md README.md
git commit -m "Document single-image docker compose deployment"
```

---

### Task 6: End-to-end manual verification

**Files:** none.

- [ ] **Step 1: Confirm the sandbox example carries the host-gateway entry**

Run: `grep -n "host-gateway" devcontainer_examples/sandbox/.devcontainer/devcontainer.json`
Expected: a line with `--add-host=host.docker.internal:host-gateway`. (Already present — no change needed; this guards against regression.)

- [ ] **Step 2: Bring the stack up via compose**

Run:
```bash
export PROJECTS_DIR="$(cd "$(git rev-parse --show-toplevel)/.." && pwd)"
docker compose up --build -d
sleep 6
curl -fsS http://host.docker.internal:8080/api/v1/health
```
Expected: healthy JSON. `PROJECTS_DIR` here points at the parent of the repo so the sandbox example path is reachable.

- [ ] **Step 3: Confirm both processes are running**

Run: `docker compose exec vibing supervisorctl -c /etc/supervisor/conf.d/vibing.conf status`
Expected: `control-plane` and `host-runtime` both `RUNNING`.

- [ ] **Step 4: Tear down**

Run: `docker compose down`
Expected: stack removed (the `vibing-data` named volume persists by design).

- [ ] **Step 5: No commit** (verification task).

---

## Self-Review Notes

- **Spec coverage:** image contents (Task 2), supervisord/fail-fast (Task 1), config reconciliation env vars (Task 2), compose + identical-path + socket (Task 4), `.env.example` + Podman (Task 4), Linux caveat doc + sandbox example (Tasks 5–6), README pointer (Task 5), manual verification (Tasks 3, 6). No `src/` changes — matches scope.
- **Placeholders:** none — every file's full content is inline.
- **Consistency:** internal port `8080` and the two `VIBING_*_URL` env names match across Dockerfile, supervisord.conf, and docs. `deploy/supervisord.conf` path matches the Dockerfile `COPY` source.
