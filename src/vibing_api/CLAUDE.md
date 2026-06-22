# vibing_api

FastAPI Control Plane. Owns API routes, SQLite state, runtime WS intake. Drives Devcontainer lifecycle directly in-process. Status is live/in-memory — never stored in SQLite.

## Files

- `main.py`: app factory, router mounting, static frontend serving.
- `api/routes/`: HTTP + WebSocket routes. Key routes:
  - `devcontainers.py`: CRUD + `start`/`stop`/`delete` lifecycle endpoints. `POST /{id}/remove-container` kills+removes the container (`devcontainer_cli.remove`) and clears live state but keeps the record. `DELETE` does the same teardown and additionally removes the DB row for manual (discovered reappears). `POST /{id}/inject-runtime`: explicit runtime injection (202, background task). `POST /{id}/stop-runtime` (202, `docker exec` kill via PID file); `GET /{id}/runtime-logs` returns `{content}` (on-demand `docker exec cat`). The devcontainer view's `runtime` is `{state: connected|launching|disconnected}` (was `runtime_connected`). `GET` endpoints compute `status` live and include a `source` field (`manual` | `discovered`).
  - `harnesses.py`: harness credential capture, `authenticate` and `install` endpoints.
  - `delegated_runs.py`: frontend-facing `delegated-runs` list (stores snapshots; not yet served to the UI).
  - `runtime.py`: `/runtime/agent/ws` — one Devcontainer Runtime per `devcontainer_id`; dispatches `harness_status` (→ `record_harness_status`) and `delegated_runs` (→ `persist_delegated_runs`); evicts harness cache on disconnect; on register, clears the runtime `launching` transient.
  - `events.py`: SSE invalidation stream for the frontend.
- `api/schemas/`: API response/request models.
- `core/live_state.py`: `LiveStateStore` — in-memory transient lifecycle status (starting/stopping/error) + last-pushed harness-status cache plus a runtime-state transient (`launching`) cleared on WS connect / launch timeout. Evicted on runtime disconnect (→ unknown, frontend `?`). Never persisted; lost on restart by design.
- `core/status_resolver.py`: `resolve_status` — transient wins if set, else live from Docker (`devcontainer.local_folder` label).
- `core/file_config.py`: reads `vibing.yaml` (sibling of `vibing.db`); exposes `devcontainers_dir` for folder discovery.
- `core/discovery.py`: non-recursive folder scan of `devcontainers_dir`; emits `DiscoveredDevcontainer` (virtual, never persisted); stable uuid5 id keyed on `local_path`.
- `core/catalog.py`: `DevcontainerCatalog` — merges manual (DB) + discovered, deduped by `local_path`. Manual record hides a discovered one at the same path. Backs all lifecycle routes so discovered ids resolve instead of 404ing.
- `core/devcontainer_service.py`: orchestrates `devcontainer up`/stop; reflects in-flight status in `LiveStateStore` (no DB status writes). Runtime injection is now an explicit endpoint, not an automatic post-start step.
- `core/runtime_injector.py`: `docker cp` + synchronous `uv tool install` (teed to one in-container log `/tmp/vibing-runtime.log`) + detached launch of the runtime with its PID in `/tmp/vibing-runtime.pid`. `inject*` return `bool` (bootstrap ok). Also `stop_runtime` (`<engine> exec` kill via PID file) and `read_log` (`<engine> exec cat`, on demand).
- `core/runtime_service.py`: `RuntimeService` — owns the `launching` transient + ~30s timeout, runtime `stop`, and on-demand `read_log`. WS connect is the durable truth; timeout/disconnect resolve to `disconnected`.
- `core/runtime_status_resolver.py`: `resolve_runtime_state` — connected (WS) wins, else `launching` transient, else `disconnected`.
- `core/runtime_channel.py`: `RuntimeRegistry` holds one `RuntimeConnection` per `devcontainer_id` and sends `command`s to it; `WebSocketRuntimeConnection` is the real adapter and owns the command wire format (via `vibing_protocol.encode`).
- `core/runtime_intake.py`: `record_harness_status` caches items in `LiveStateStore` (no DB write); `persist_delegated_runs` writes to `delegated_runs` table.
- `core/broadcaster.py`: SSE invalidation fan-out.
- `core/database.py`, `core/schema.py`: SQLite setup and schema (version 8). Tables: `app_meta`, `devcontainers` (no `status` column), `harness_credentials`, `delegated_runs`. `harness_status` table removed.
- `repositories/`: SQL only. `devcontainers.py`, `harness_credentials.py`, `delegated_runs.py`. Callers commit transactions.
- `cli/dev.py`: dev helpers, mounted as `vibing dev ...`.

## Context

- `/runtime/agent/ws`: one Devcontainer Runtime per devcontainer id (no host worker endpoint).
- Devcontainer `status` is computed live on every request (transient → Docker label) — never stored in DB.
- Harness status is cached in-memory per devcontainer; unknown (`?` in frontend) when no runtime is connected.
- `source` field on devcontainer responses: `manual` (DB row) | `discovered` (virtual, from folder scan).
- Tests: `tests/api`.
