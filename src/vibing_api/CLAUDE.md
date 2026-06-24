# vibing_api

FastAPI Control Plane. Owns API routes, SQLite state, runtime WS intake. Drives Devcontainer lifecycle directly in-process, and owns harness install/auth/status via `devcontainer exec` (ADR-0019). Status is live/in-memory — never stored in SQLite.

## Files

- `main.py`: app factory, router mounting, static frontend serving.
- `api/routes/`: HTTP + WebSocket routes. Key routes:
  - `devcontainers.py`: CRUD + `start`/`stop`/`delete` lifecycle endpoints. `POST /{id}/remove-container` kills+removes the container (`devcontainer_cli.remove`) and clears live state but keeps the record. `DELETE` does the same teardown and additionally removes the DB row. `POST /{id}/inject-runtime`: explicit runtime injection (202, background task). `POST /{id}/stop-runtime` (202, `docker exec` kill via PID file); `GET /{id}/runtime-logs/stream` streams log via `tail -n +1 -f` (`text/plain`, chunked HTTP). The devcontainer view's `runtime` is `{state: connected|launching|disconnected}`. `GET` endpoints compute `status` live from transient + Docker label.
  - `harnesses.py`: `install` and `authenticate` as **synchronous streaming POST** endpoints (chunked HTTP) that run via `DevcontainerExecutor` and pipe `devcontainer exec` output live; on completion recompute + cache status and SSE-invalidate. `GET /{id}/harnesses` serves cached status, and **self-heals**: if the cache is empty but the container is running (vibing didn't start it — already up before vibing, or a restart), it computes + caches on demand so status never stays `known=false` forever. `POST /{id}/harnesses/refresh` recomputes on demand. No longer sends runtime Commands (ADR-0019).
  - `delegated_runs.py`: frontend-facing `GET /{id}/delegated-runs` — serves the list from the in-memory `LiveStateStore` cache (`live_state.get_delegated_runs`); 404 for unknown id.
  - `runtime.py`: `/runtime/agent/ws` — one Devcontainer Runtime per `devcontainer_id`; dispatches `delegated_runs` (→ `record_delegated_runs`); on register, clears the runtime `launching` transient. No `harness_status` intake, no command sending (channel is outbound-only, ADR-0019).
  - `events.py`: SSE invalidation stream for the frontend.
- `api/schemas/`: API response/request models.
- `core/live_state.py`: `LiveStateStore` — in-memory transient lifecycle status (starting/stopping/error) + a CP-computed harness-status cache (keyed to container-running; recomputed on container start, post-install/auth, manual refresh, and lazily on GET when running but uncached — not evicted on runtime disconnect) plus a runtime-state transient (`launching`, or sticky `error` on inject failure) cleared on WS connect / launch timeout / retry inject, plus a container-scoped delegated-runs snapshot cache (set by the runtime channel, evicted on container teardown, rebuilt on runtime reconnect). Never persisted; lost on restart by design.
- `core/status_resolver.py`: `resolve_status` — transient wins if set, else live from Docker (`devcontainer.local_folder` label).
- `core/file_config.py`: reads `vibing.yaml` (sibling of `vibing.db`); exposes `devcontainers_dir` for folder discovery.
- `core/discovery.py`: non-recursive folder scan of `devcontainers_dir`; emits `DiscoveredDevcontainer` (name, local_path, stable uuid5 id keyed on `local_path`). `is_devcontainer_folder` and `devcontainer_id` helpers used by sync and routes.
- `core/devcontainer_store.py`: `DevcontainerStore` — DB-only resolver (replaces the catalog merge). After startup sync every devcontainer is a real row; resolution is a plain DB read.
- `core/devcontainer_sync.py`: startup filesystem reconcile. Upserts every scanned folder; evicts rows whose folder no longer has `.devcontainer/` (manual rows included) and clears their live-state caches. Runs Docker-free at startup.
- `core/devcontainer_service.py`: orchestrates `devcontainer up`/stop; reflects in-flight status in `LiveStateStore` (no DB status writes). Runtime injection is now an explicit endpoint, not an automatic post-start step.
- `core/runtime_injector.py`: two-phase `inject()` — `_bootstrap` (`docker cp` uv + wheel, synchronous `uv tool install` teed to `/tmp/vibing-runtime.log`, then a `vibing runtime preflight` HTTP probe of the control-plane `/api/v1/health`) then, **only on success**, `_spawn` (reap any prior runtime — it would still hold the MCP port and break the new bind — then a detached `nohup` launch with PID in `/tmp/vibing-runtime.pid`). Two separate `devcontainer exec` calls; the same resolved control-plane URL is used by both the preflight and the launch. `inject*` return `bool` (bootstrap+preflight ok). Also `stop_runtime` (`<engine> exec` kill via PID file) and `stream_log` (async generator, `tail -n +1 -f` via injectable `log_streamer`).
- `core/runtime_service.py`: `RuntimeService` — owns the `launching` transient + ~30s timeout, runtime `stop`, and live log streaming (`stream_log`). WS connect is the durable truth; timeout/disconnect resolve to `disconnected`. On inject failure (bootstrap or preflight) it sets a sticky `error` transient (retry inject overwrites it with `launching`); the ~30s timeout still resolves to `disconnected`.
- `core/runtime_status_resolver.py`: `resolve_runtime_state` — connected (WS) wins, else `launching` transient, else `error` transient, else `disconnected`.
- `core/runtime_channel.py`: `RuntimeRegistry` holds one `RuntimeConnection` per `devcontainer_id` for liveness/intake (the `connected` runtime state). No command sending — the channel is outbound-only (ADR-0019).
- `core/devcontainer_executor.py`: `DevcontainerExecutor(local_path)` — the `vibing_harness.Executor` impl over `devcontainer exec` (remoteUser-correct; **never** raw `docker exec`). PIPE-based runner (distinct from `DevcontainerCliAdapter`'s temp-file `_default_runner`) so it can `stream()` install output live and pipe creds to stdin; `run` recovers the in-container exit code via a `__rc=N__` shell marker. The default runner logs each exec command and its output tail (like `devcontainer_cli`).
- `core/harness_service.py`: harness install/authenticate/status driven through a `DevcontainerExecutor` + `vibing_harness` descriptors. `install_stream`/`authenticate_stream` yield live output; `refresh`/`compute_status` compute and cache status in `LiveStateStore` and publish the `harnesses` SSE.
- `core/runtime_intake.py`: `record_delegated_runs` stores snapshots in `LiveStateStore` and publishes SSE invalidation.
- `core/broadcaster.py`: SSE invalidation fan-out.
- `core/database.py`, `core/schema.py`: SQLite setup and schema (version 9). Tables: `app_meta`, `devcontainers` (no `status` column), `harness_credentials`. `harness_status` and `delegated_runs` tables removed; `_drop_legacy` drops both idempotently.
- `repositories/`: SQL only. `devcontainers.py`, `harness_credentials.py`. Callers commit transactions.
- `cli/dev.py`: dev helpers, mounted as `vibing dev ...`.

## Context

- `/runtime/agent/ws`: one Devcontainer Runtime per devcontainer id (no host worker endpoint).
- Devcontainer `status` is computed live on every request (transient → Docker label) — never stored in DB.
- Harness status is CP-computed via `devcontainer exec` and cached in-memory per devcontainer; keyed to container-running (visible even with the runtime down), unknown (`?` in frontend) only when the container is not running. Recomputed on container start, post-install/auth, manual refresh, and lazily on GET when running but uncached.
- Devcontainers are reconciled with the filesystem at startup (new folders surface after restart or POST; stale rows evicted). No `source` field on responses.
- Tests: `tests/api`.
