# Vibing Overview

Vibing is local-first developer tooling for orchestrating AI coding agents across isolated devcontainers.

The current agent is Claude Code. The product treats "agent" as a role, not a hard-wired vendor.

## Domain Language

Canonical glossary: [`CONTEXT.md`](../CONTEXT.md).

- **Devcontainer:** persistent isolated container bound to one local folder (`local_path`).
- **Agent Session:** one coding-agent run inside a running Devcontainer.
- **Control Plane:** FastAPI + SQLite backend. Sends Commands and projects Runtime Events.
- **Runtime:** worker process connected to the Control Plane.
- **Command:** Control Plane request to a runtime.
- **Runtime Event:** append-only event emitted by a runtime.
- **Inbox Event:** read-model projection for questions, approvals, failures, completions.

## Architecture Decisions

ADRs live in [`docs/adr/`](adr/).

- [ADR-0001](adr/0001-devcontainer-source-is-a-single-local-path.md): Devcontainer source is one `local_path`, not generic source descriptors.
- [ADR-0002](adr/0002-inbox-is-a-projection-of-the-runtime-event-stream.md): `runtime_events` is the append-only source of truth. Read models are projections.
- [ADR-0003](adr/0003-runtimes-connect-to-the-control-plane-over-tcp-ip-in-a-star-topology.md): runtimes connect to Control Plane over TCP/IP in a star topology.
- [ADR-0004](adr/0004-devcontainer-runtime-agents-connect-on-a-dedicated-endpoint-routed-by-devcontainer-id.md): devcontainer agents connect on a dedicated endpoint routed by `devcontainer_id`.

## Package Shape

This repo has one root uv Python package plus a separate frontend app source tree.

- `src/vibing_cli`: root `vibing` Typer CLI.
- `src/vibing_api`: FastAPI Control Plane.
- `src/vibing_protocol`: shared command/event/envelope types.
- `src/vibing_runtime_client`: shared runtime WebSocket client.
- `src/vibing_host_runtime`: host worker.
- `src/vibing_devcontainer_runtime`: in-container agent worker.
- `apps/web`: React/Vite frontend source.

The frontend may be built and served by the backend/container, but its source stays in `apps/web`.

## Lifecycles

Devcontainer lifecycle:

```text
created -> starting -> running -> stopping -> stopped
                         \-----------------> error
```

Stopping a devcontainer ends any active agent session inside it.

Agent Session lifecycle:

```text
starting -> running <-> waiting_for_approval -> completed
                                           \--> failed
                                           \--> stopped
```

Stopping an agent session leaves the devcontainer running.

## Runtime Transport

The Control Plane exposes two runtime WebSocket endpoints:

- `/api/v1/runtime/ws`: one Host Runtime Worker, source `host_runtime_worker`.
- `/api/v1/runtime/agent/ws`: one Devcontainer Runtime Agent per devcontainer id, source `devcontainer_runtime_agent`.

The Host Runtime Worker runs:

```bash
uv run vibing host-runtime
```

Defaults:

| Flag | Default | Purpose |
| --- | --- | --- |
| `--control-plane-url` | `ws://127.0.0.1:8000/api/v1/runtime/ws` | Host worker WebSocket. |
| `--devcontainer-cli` | `devcontainer` | Dev Container CLI binary. |
| `--agent-control-plane-url` | `ws://host.docker.internal:8000/api/v1/runtime/agent/ws` | URL injected into the container agent. |

After a successful `devcontainer up`, the host worker injects the runtime (`docker cp`
of `uv` + the `vibing` wheel, `uv tool install`, then a detached exec) and starts:

```bash
vibing devcontainer-runtime --devcontainer-id <id>
```

The devcontainer image does not need `vibing` pre-installed. It must provide `claude`
(authenticated), network egress, and on Linux the host-gateway `runArgs` entry.
See [`docs/deployment.md`](deployment.md#devcontainer-contract).

## Devcontainer Lifecycle API

With the host worker connected:

```bash
curl -X POST http://localhost:8000/api/v1/devcontainers/<id>/start
curl -X POST http://localhost:8000/api/v1/devcontainers/<id>/stop
```

Both return `202 Accepted`. State changes arrive later as Runtime Events and projected read-model updates.

- Start maps to `devcontainer up`.
- Stop maps to `devcontainer stop`.
- Stop preserves the reusable environment. It does not delete the container.
- No `restart_devcontainer` command exists. Restart is stop then start.

## MVP Scope

- Local-only, single-user workflow.
- Devcontainer dashboard.
- Devcontainers created from local folders only.
- One persistent isolated devcontainer per project.
- Claude Code support.
- One active agent session per devcontainer.
- Live session view and structured agent-session status.
- Centralized approval queue.
- Inbox for questions, approvals, failures, completions.
- Direct editing via VS Code, native editor, or browser editor.
- Basic Git status and changed-files view.
- Important event history and final session summaries.

## MVP Non-Goals

- Git URL creation or repo cloning.
- Codex or other coding agents.
- Multiple concurrent agent sessions per devcontainer.
- Cloud sync, hosted execution, remote workers.
- Multi-user collaboration.
- Kubernetes.
- Workflow builder or plugin SDK.
- Session Output / terminal scrollback persistence.

## Local-First Assumptions

- Runs entirely on the developer's machine.
- No auth, no remote accounts.
- Single user, single host.
- Backend and frontend bind locally.
- Runtime channel is local-only and unauthenticated.
- SQLite file stores metadata.
- `runtime_events` is the source of truth.

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

## Status

Early MVP. Foundation implemented; core decisions landed.

- Workspace to Devcontainer rename is complete.
- Schema uses single `local_path`.
- Persistence is behind per-entity repositories.
- Route handlers contain no SQL.
- Read-model state is produced by reducer projections over `runtime_events`.
- Runtime transport is in place for Devcontainer and Agent Session lifecycles.
- Session Output live terminal stream is still deferred.

## More Docs

- [MVP Product Requirement Document](https://rainbowhunter.atlassian.net/wiki/spaces/V/pages/2097153/Vibing+MVP+Product+Requirement+Document)
- [MVP Architecture](https://rainbowhunter.atlassian.net/wiki/spaces/V/pages/2293790/Vibing+MVP+Architecture)
- [`docs/foundation-api.md`](foundation-api.md): foundation HTTP API examples.
- [`CONTEXT.md`](../CONTEXT.md): canonical glossary.
- [`docs/adr/`](adr/): architectural decisions.

## Lockfiles

Both lockfiles are committed and should stay in sync with their manifests:

- `uv.lock`
- `apps/web/pnpm-lock.yaml`
