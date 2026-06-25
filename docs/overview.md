# Vibing Overview

Vibing is a local control panel for running coding harnesses across isolated devcontainers.

## Domain Language

Canonical glossary: [`CONTEXT.md`](../CONTEXT.md).

- **Devcontainer:** persistent isolated container bound to one local folder (`local_path`).
- **Control Plane:** FastAPI + SQLite backend. Drives the Devcontainer lifecycle in-process. Mutates read-model state directly — no event log.
- **Devcontainer Runtime:** in-container companion process. Manages harness credentials, reports Harness Status, hosts MCP delegation server.
- **Coding Harness:** installable CLI coding agent (`claude`, `codex`, `cursor-agent`).
- **Harness Status:** the runtime's report of a managed harness's `installed`/`authenticated` state.
- **Delegated Run:** one-shot managed harness execution spawned via MCP; in-container only, not tracked by the Control Plane.
- **Command:** Control Plane → Devcontainer Runtime message (`authenticate_harness`).

## Architecture Decisions

ADRs live in [`docs/adr/`](adr/).

Key decisions:
- [ADR-0001](adr/0001-devcontainer-source-is-a-single-local-path.md): Devcontainer source is one `local_path`.
- [ADR-0011](adr/0011-delegated-runs-are-in-container-only-and-observed-via-mcp.md): Delegated Runs are in-container, observed via MCP.
- [ADR-0012](adr/0012-harness-credentials-are-host-captured-stored-plaintext-and-injected-per-container.md): Harness Credentials stored plaintext, injected per-container.
- [ADR-0014](adr/0014-the-control-plane-drives-devcontainers-directly-and-the-event-log-is-removed.md): Control Plane drives Devcontainers directly; event log removed.
- [ADR-0015](adr/0015-drop-the-agent-session-model-the-devcontainer-runtime-is-a-harness-friction-companion.md): Agent Session model dropped; Devcontainer Runtime is a harness companion.

## Package Shape

This repo has one root uv Python package plus a separate frontend app source tree.

- `src/vibing_cli`: root `vibing` Typer CLI.
- `src/vibing_api`: FastAPI Control Plane.
- `src/vibing_protocol`: shared command/envelope/harness-status types.
- `src/vibing_devcontainer_runtime`: in-container companion (harness management + MCP).
- `apps/web`: React/Vite frontend source.

## Lifecycle

Devcontainer lifecycle — owned by the Control Plane:

```text
created -> starting -> running -> stopping -> stopped
                         \-----------------> error
```

Start maps to `devcontainer up`; the Control Plane also injects and launches the Devcontainer Runtime after a successful up. Stop stops the container without deleting its reusable environment. Restart is stop then start.

HTTP endpoints return `202 Accepted`; the Control Plane runs the CLI in a background task, writing status directly as it progresses. The browser sees changes via SSE invalidation.

## Runtime Transport

The Control Plane exposes one runtime WebSocket endpoint:

- `/api/v1/runtime/agent/ws`: one Devcontainer Runtime per `devcontainer_id`.

The runtime channel carries exactly three message kinds: `register`, `command` (Control Plane → Runtime), and `harness_status` (Runtime → Control Plane).

On connect the Devcontainer Runtime sends `register`, then immediately reports Harness Status for each managed harness. When the Control Plane sends `authenticate_harness`, the runtime installs and authenticates the harness, then reports updated Harness Status.

## Harness Credential + Status Workflow

1. User runs `vibing harness capture <harness>` on the host; credentials are stored plaintext in the Control Plane (ADR-0012).
2. On devcontainer start, the Control Plane injects and launches `vibing devcontainer-runtime`.
3. The runtime connects, registers, and reports initial Harness Status.
4. `POST /api/v1/devcontainers/{id}/harnesses/{harness}/authenticate` sends `authenticate_harness` with credentials.
5. The runtime installs/authenticates the harness and reports updated Harness Status.
6. The Control Plane writes the status to the read model and publishes SSE invalidation.

## MCP Delegation

The Devcontainer Runtime hosts a streamable-HTTP MCP server (default `127.0.0.1:8848`). The main harness (Claude Code) calls it to spawn Delegated Runs (`spawn`, with a required `title`), list them (`list_runs`), fetch a run's result (`get_run`), block until a detached run finishes (`await_run`), and stop them (`stop`). The server carries `instructions` framing these as *external subagents* (see `external-subagent-guide.md`). Delegated Runs are in-container only; the Control Plane does not track them.

## Devcontainer Runtime Injection

After a successful `devcontainer up`, the Control Plane:

1. `docker cp`s `uv` and the `vibing` wheel into the container.
2. Runs `uv tool install` inside the container.
3. Detached-execs `vibing devcontainer-runtime --devcontainer-id <id>`.

The devcontainer image does not need `vibing` pre-installed. It must provide a package manager, network egress (to resolve deps and reach the Anthropic API), and on Linux the host-gateway `runArgs` entry. See [`docs/deployment.md`](deployment.md#devcontainer-contract).

## Devcontainer Lifecycle API

```bash
curl -X POST http://localhost:8000/api/v1/devcontainers/<id>/start
curl -X POST http://localhost:8000/api/v1/devcontainers/<id>/stop
```

Both return `202 Accepted`. State changes are written directly by the Control Plane as the Dev Container CLI progresses.

## Environment

Backend settings use the `VIBING_` prefix.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VIBING_DATABASE_URL` | `sqlite:///./vibing.db` | SQLite URL. Only `sqlite:///` is supported. |
| `VIBING_STATIC_DIR` | unset | Built frontend bundle directory for SPA serving. |
| `VIBING_BACKEND_HOST` | `0.0.0.0` | Reported by settings endpoint. Pass `--host` to uvicorn to bind. |
| `VIBING_BACKEND_PORT` | `8080` | Reported by settings endpoint. Pass `--port` to uvicorn to bind. |
| `VIBING_APP_NAME` | `vibing-api` | App name in OpenAPI / health responses. |
| `VIBING_API_V1_PREFIX` | `/api/v1` | Prefix for all v1 routes. |

The frontend has no env vars. It calls `/api/v1/*`.

## Sample Data

Local UI development only:

```bash
uv run vibing dev sample_data seed
uv run vibing dev sample_data status
uv run vibing dev sample_data reset
```

Sample row ids start with `sample-`; sample names start with `[sample]`. Reset does not touch real rows.

## More Docs

- [`docs/foundation-api.md`](foundation-api.md): foundation HTTP API examples.
- [`CONTEXT.md`](../CONTEXT.md): canonical glossary.
- [`docs/adr/`](adr/): architectural decisions.

## Lockfiles

Both lockfiles are committed and should stay in sync with their manifests:

- `uv.lock`
- `apps/web/pnpm-lock.yaml`
