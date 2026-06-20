# vibing_api

FastAPI Control Plane. Owns API routes, SQLite state, runtime WS intake. Drives Devcontainer lifecycle directly in-process. Mutates read-model state directly — no event log or reducer.

## Files

- `main.py`: app factory, router mounting, static frontend serving.
- `api/routes/`: HTTP + WebSocket routes. Key routes:
  - `devcontainers.py`: CRUD + `start`/`stop` lifecycle endpoints.
  - `harnesses.py`: harness credential capture, `authenticate` and `install` endpoints.
  - `delegated_runs.py`: frontend-facing `delegated-runs` list (empty stub; CP stores snapshots but does not serve them to the UI yet).
  - `runtime.py`: `/runtime/agent/ws` — one Devcontainer Runtime per `devcontainer_id`.
  - `events.py`: SSE invalidation stream for the frontend.
- `api/schemas/`: API response/request models.
- `core/devcontainer_service.py`: orchestrates `devcontainer up`/stop, runtime injection, and direct read-model writes.
- `core/runtime_injector.py`: `docker cp` + `uv tool install` + detached exec of `vibing devcontainer-runtime`.
- `core/runtime_channel.py`: runtime WS manager; routes `register`, `harness_status`, and `delegated_runs` messages; sends `command` envelopes.
- `core/commands.py`: builds typed `authenticate_harness` Command envelopes.
- `core/broadcaster.py`: SSE invalidation fan-out.
- `core/database.py`, `core/schema.py`: SQLite setup and schema.
- `repositories/`: SQL only. `devcontainers.py`, `harness_credentials.py`, `harness_status.py`, `delegated_runs.py`. Callers commit transactions.
- `cli/dev.py`: dev helpers, mounted as `vibing dev ...`.

## Context

- `/runtime/agent/ws`: one Devcontainer Runtime per devcontainer id (no host worker endpoint).
- State is written directly when CLI operations complete or Harness Status arrives — no projection step.
- Tests: `tests/api`.
