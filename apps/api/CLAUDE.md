# apps/api — Control Plane (FastAPI + SQLite)

The backend hub. Sends Commands to runtimes and projects the Runtime Events they emit
into all read-model state. Read the root `CONTEXT.md` for domain terms and `docs/adr/` for
the load-bearing decisions: single `local_path` (ADR-0001), `runtime_events` as the sole
source of truth with read-model as a projection (ADR-0002), star-topology transport (ADR-0003).

Workspace package, depends on `packages/protocol` and `packages/host_runtime` (editable path
deps). Use `uv` only — never edit `pyproject.toml` by hand. `uv run pytest -q`; `uv run vibing dev sample_data {seed,reset,status}`.

## Where things live

- `src/vibing_api/main.py` — app factory: wires routers under `/api/v1`, mounts SPA fallback, applies schema on startup.
- `src/vibing_api/api/routes/` — HTTP endpoints; thin, no SQL, raise HTTP 404s here.
  - `devcontainers.py` — devcontainer CRUD + lifecycle `POST /{id}/start|stop` (validate state, send Command to the worker via the runtime manager; 202, no status mutation).
  - `agent_sessions.py` — `POST /devcontainers/{id}/agent-sessions` (guards: DC exists → running → agent connected → no active session; creates row as `starting`, sends `start_agent_session` command to agent, returns 202). `POST /devcontainers/{id}/agent-sessions/{session_id}/stop` (guards: DC exists → session exists/belongs → session active → agent connected; sends `stop_agent_session`, returns 202 without mutating status — `session_stopped` event drives projection).
  - `health.py`, `status.py`, `config.py`, `settings.py`, `diagnostics.py` — health, version/status, runtime config, settings, local prerequisite checks.
  - `runtime.py` — runtime WebSocket channels: `/runtime/ws` (host worker) + `/runtime/agent/ws` (per-devcontainer agent, keyed by `devcontainer_id`); both do registration + RuntimeEvent intake (ADR-0003/ADR-0004).
  - Request/response examples for all the above: [`docs/foundation-api.md`](../../docs/foundation-api.md).
- `src/vibing_api/api/schemas/` — Pydantic request/response models (`devcontainers.py`, `agent_sessions.py`, shared `common.py` error shapes).
- `src/vibing_api/repositories/` — per-entity SQL wrappers over `sqlite3.Connection`. **Execute but never commit; never raise HTTP errors.** Caller owns the transaction.
  - `devcontainers.py`, `agent_sessions.py` (includes `get_active_by_devcontainer` → active statuses: starting/running/waiting_for_approval), `runtime_events.py`, `approvals.py`, `inbox.py`, `summaries.py`.
- `src/vibing_api/core/` — domain core.
  - `reducer.py` — **sole writer of derived state**: pure `reduce(event)` + I/O `project(event, conn)` over the event stream (ADR-0002).
  - `schema.py` — single source of truth for the on-disk SQLite shape; `apply_schema` is idempotent (no migrations — schema change ⇒ wipe the dev DB).
  - `vocabularies.py` — typed `Literal` status/event vocabularies.
  - `config.py` — `VIBING_`-prefixed settings. `database.py` — connection helper. `errors.py` — error envelope + handlers (`AGENT_SESSION_ACTIVE`, `AGENT_SESSION_NOT_FOUND`, `AGENT_SESSION_NOT_ACTIVE` codes; `ActiveAgentSessionError`, `AgentSessionNotFoundError`, `InactiveAgentSessionError`; `RuntimeUnavailableError` accepts optional message). `commands.py` — re-export shim for `vibing_protocol.commands`.
  - `runtime_channel.py` — `RuntimeConnectionManager` (single host-worker slot) + `AgentConnectionManager` (per-devcontainer agent slots, `dict[devcontainer_id, WebSocket]`) + `persist_runtime_event` (record + project an inbound RuntimeEvent).
- `src/vibing_api/cli/dev.py` — `vibing dev` Typer commands (sample-data seed/reset/status).
- `src/vibing_api/dev/sample_data.py` — curated sample rows (ids prefixed `sample-`).
- `tests/` — pytest; one `test_*.py` per module.

## Conventions

- Routes never hold SQL; repositories never raise HTTP; the reducer is the only writer of read-model state.
- New status/event values go in `core/vocabularies.py`; new on-disk columns go in `core/schema.py`.
