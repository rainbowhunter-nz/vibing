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

> **Security:** mounting the engine socket gives the container control of your
> host's container engine — effectively host-root access. Vibing is a local,
> single-user tool; only run it on a machine you trust and do not expose port
> 8080 beyond localhost.

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

## Devcontainer contract

Vibing injects the Devcontainer Runtime Agent when a devcontainer starts — it
copies `uv` and the `vibing` wheel from the Control Plane image into the
container and runs `uv tool install` before launching `vibing devcontainer-runtime`.
Your project's devcontainer image does **not** need Vibing-specific packages.

Each devcontainer must provide:

- **`claude` on `PATH`, authenticated** — agent sessions invoke Claude Code.
- **Network egress** — injection resolves Python deps online; the agent calls the Anthropic API.
- **Linux: host-gateway `runArgs`** — see the Linux caveat above so
  `host.docker.internal` resolves inside the container.

See [`devcontainer_examples/sandbox/README.md`](../devcontainer_examples/sandbox/README.md)
and [ADR-0004](adr/0004-devcontainer-runtime-agents-connect-on-a-dedicated-endpoint-routed-by-devcontainer-id.md).

## Verify end-to-end

1. `docker compose up --build`, then open the UI.
2. Create a devcontainer whose `local_path` is a folder under `PROJECTS_DIR`.
3. Start it; confirm the container appears on the host (`docker ps`) and the
   agent-session reaches `running`.
