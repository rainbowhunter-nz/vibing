# Single-Image Docker-out-of-Docker Deployment

Date: 2026-06-02
Status: Approved

## Goal

Package the whole application — Control Plane, frontend, and Host Runtime Worker —
into one Docker image, brought up by a single `docker compose` file in a
docker-out-of-docker (DooD) configuration. The user mounts a host projects
directory and the container engine socket; one `docker compose up` runs everything.

Scope: packaging + compose + docs only. **No `src/` changes.**

## Constraints That Shape The Design

- **DooD path aliasing.** The Host Runtime Worker shells out to `devcontainer up
  --workspace-folder <local_path>`. The devcontainer CLI drives the *host* daemon
  through the mounted socket, so the host daemon resolves the workspace bind-mount.
  The `local_path` stored by the Control Plane must therefore resolve to the same
  files inside the vibing container and on the host.
- **Two long-running processes** share one container: uvicorn (control plane +
  static frontend) and `vibing host-runtime`.
- **Podman support.** The socket mount is user-editable; we do not hardcode Docker.

## Decisions

1. **One container, both processes**, managed by `supervisord` as PID 1. If either
   process exits, the container exits (fail-fast).
2. **Identical-path passthrough** for projects: user mounts host projects dir at the
   same absolute path inside the container (`${PROJECTS_DIR}:${PROJECTS_DIR}`). No
   path-translation code. The UI's `local_path` is a real host path.
3. **Published port 8080**, matching the existing Dockerfile.
4. Packaging only — no application code changes.

## Architecture

```
HOST (Docker/Podman daemon)
 ├─ vibing container  ← the image we build
 │    ├─ uvicorn (control plane + frontend)            :8080
 │    └─ vibing host-runtime ─connects→ ws://127.0.0.1:8080/api/v1/runtime/ws
 │    mounts:
 │      - ${PROJECTS_DIR}:${PROJECTS_DIR}    (identical path)
 │      - container engine socket            (user-supplied)
 │      - vibing-data:/data                  (SQLite)
 │
 └─ devcontainers  ← started by host-runtime via `devcontainer up` on the HOST daemon
        └─ vibing devcontainer-runtime ─connects→
             ws://host.docker.internal:8080/api/v1/runtime/agent/ws
```

Both vibing processes share `127.0.0.1` inside the single container. Started
devcontainers are siblings on the host daemon and call the control plane back
through `host.docker.internal:8080` (the published port).

## Image (extend `Dockerfile` final stage)

Current final stage: `python:3.13-slim` + uv + built frontend, runs uvicorn only.
Add what the host-runtime needs:

- **Node.js 24** + `@devcontainers/cli` (the `devcontainer` binary).
- **docker CLI** client (the devcontainer CLI invokes it against the mounted socket).
- **git** (devcontainer features commonly require it).
- **supervisord**, PID 1, running both programs; output to stdout, per-program prefix.

Keep the existing build stage (frontend) and the Python install layers unchanged.

### Process management

`supervisord` config runs two programs:

- `control-plane`: `uvicorn vibing_api.main:app --host 0.0.0.0 --port 8080`
- `host-runtime`: `vibing host-runtime --control-plane-url <ws> --agent-control-plane-url <ws>`

Both with `autorestart=false` and `supervisor` configured so a fatal exit of
either stops the container (fail-fast). Logs to stdout/stderr.

## Config Reconciliation

The host-runtime defaults to `ws://127.0.0.1:8000`; the image serves `:8080`. Fixed
via flags/env at launch — no code change:

- `VIBING_CONTROL_PLANE_URL` default `ws://127.0.0.1:8080/api/v1/runtime/ws`
- `VIBING_AGENT_CONTROL_PLANE_URL` default `ws://host.docker.internal:8080/api/v1/runtime/agent/ws`

supervisord passes these to `vibing host-runtime`. Existing image env stays:
`VIBING_DATABASE_URL=sqlite:////data/vibing.db`, `VIBING_STATIC_DIR=/repo/dist`.

## docker-compose.yml

```yaml
services:
  vibing:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - vibing-data:/data
      - ${PROJECTS_DIR}:${PROJECTS_DIR}            # identical-path passthrough
      - /var/run/docker.sock:/var/run/docker.sock  # edit for Podman (see .env.example)
    environment:
      - PROJECTS_DIR=${PROJECTS_DIR}
volumes:
  vibing-data:
```

`.env.example` documents:

- `PROJECTS_DIR` — absolute host path to the directory containing projects.
- Podman socket variant, e.g. `${XDG_RUNTIME_DIR}/podman/podman.sock:/var/run/docker.sock`.

The socket line is left as a literal the user adjusts, per requirement.

## Known Caveat (documented, not solved)

On **Linux**, sibling devcontainers do not get `host.docker.internal` automatically;
the devcontainer needs `--add-host=host.docker.internal:host-gateway` or the
equivalent in its `devcontainer.json`. On Docker Desktop (Mac/Win) it works out of
the box. Document this in the deployment doc and add the host-gateway entry to the
`devcontainer_examples/sandbox` example so it works end-to-end.

## Verification

No unit-testable logic is added. Verification is a documented manual smoke test:

1. `PROJECTS_DIR=<abs path> docker compose up --build`
2. `curl http://localhost:8080/api/v1/health` → ok
3. Open UI, create a devcontainer with `local_path` under `PROJECTS_DIR`, start it.
4. Confirm the container comes up on the host and the agent connects back
   (agent-session reaches `running`).

## Deliverables

- Updated `Dockerfile` (Node + devcontainer CLI + docker CLI + git + supervisord).
- `supervisord.conf` (or inline) for the two programs.
- `docker-compose.yml`.
- `.env.example`.
- Deployment doc (e.g. `docs/deployment.md`) covering mount convention, Podman socket,
  and the Linux `host.docker.internal` caveat.
- `host-gateway` entry added to `devcontainer_examples/sandbox`.
- README pointer to the compose deployment.

## Out Of Scope

- Path-translation layer (identical-path passthrough chosen instead).
- Multi-user / remote deployment, TLS, auth.
- Persisting session output.
- Any `src/` change.
