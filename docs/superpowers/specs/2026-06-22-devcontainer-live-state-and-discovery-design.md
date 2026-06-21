# Devcontainer detail-view features: live state + folder discovery

Date: 2026-06-22

## Summary

Improve the devcontainer detail view and unify the devcontainer data model around a
principle: **never store in the DB anything retrievable live from the container engine or
the Devcontainer Runtime.** Two kinds of state move out of SQLite into in-memory/live
sources:

- **Lifecycle status** (`running`/`stopped`/...) — derived live from Docker, with an
  in-memory transient map for in-flight `starting`/`stopping`/`error`.
- **Harness install/auth status** — an in-memory cache populated by the runtime's pushed
  status envelopes, evicted on disconnect (unknown → `?`).

On top of that model, add detail-view UX (icon control buttons, a Delete button that kills
and removes the container, a manual Inject-Runtime button, an install spinner that lasts
until completion) and config-driven **folder discovery** of devcontainers that are never
persisted.

## Motivation

The current model persists `harness_status` and the devcontainer `status` column in SQLite
and writes to them as operations complete. That duplicates state the system can observe
live, and it forces discovered (folder-sourced) devcontainers — which have no DB row — to
behave differently from manually-created ones. Centering on live state makes both kinds
behave identically and removes a table, a column, and their persist paths.

## Principle

> Never store what can be retrieved live.

- Container running/stopped → live from Docker (`devcontainer.local_folder` label).
- Harness installed/authenticated → live from the connected Devcontainer Runtime.
- Runtime connected? → already in-memory (`RuntimeRegistry`).
- In-flight operation transient states (`starting`/`stopping`/`error`) → in-memory, ephemeral.
- Record metadata (`name`, `local_path`, `created_at`, `updated_at`) for *manually
  created* devcontainers → legitimately stored; it is not live state.

## Data model changes

### `devcontainers` table
- **Drop the `status` column.** Keeps `id`, `name`, `local_path`, `created_at`, `updated_at`.
- Discovered devcontainers are **never** written here.

### `harness_status` table
- **Removed entirely**, along with its repository and the `runtime_intake` persist path.
  Replaced by an in-memory cache.

### Status vocabulary
- `created` folds into `stopped` (a never-started devcontainer has no container → `stopped`).
- Live state machine: `stopped → starting → running → stopping → stopped`, plus `error`.
- Transitions: **start** allowed when not `running`; **stop** allowed when `running`.

## In-memory live state

Lives alongside the existing in-memory `RuntimeRegistry`:

1. **Harness-status cache** — keyed by `devcontainer_id`, holds the last status envelope the
   runtime pushed (on register and after each install/authenticate command). Evicted when
   that runtime disconnects. Frontend reads it; absent → `?` (unknown).
2. **Lifecycle transient map** — keyed by `devcontainer_id`, holds `starting`/`stopping`/
   `error` while an operation is in flight. Set when an op begins, cleared on success
   (live Docker status takes over), set to `error` on failure (cleared when the next start
   begins). Lost on restart — ephemeral by design.

## Live status resolver

A single resolver answers status for any devcontainer (manual or discovered):

1. If the lifecycle transient map has an entry for the id → return it
   (`starting`/`stopping`/`error`).
2. Else read live from Docker: a running container with
   `label=devcontainer.local_folder=<local_path>` → `running`; none → `stopped`.

The Docker read is one batched query per list request (e.g.
`docker ps --format '{{.Label "devcontainer.local_folder"}}'` → a set of running folders),
not one call per devcontainer.

`DevcontainerService` no longer writes status to the DB. Each operation: set transient →
broadcast SSE → run CLI → clear/`error` transient → broadcast SSE.

## Folder discovery (virtual, never stored)

### Config file
- `vibing.yaml`, default location = same directory as `vibing.db` (parsed from
  `database_url`). Overridable via `VIBING_CONFIG_FILE`.
- Shape:
  ```yaml
  devcontainers_dir: /abs/path/to/devcontainers
  ```
- File or key absent → discovery is off. Requires adding a YAML parser dependency
  (`pyyaml`) via `uv`.

### Scan
- **Non-recursive.** Each immediate subdirectory of `devcontainers_dir` that contains a
  `.devcontainer/` folder → one discovered devcontainer.
- `name` = subdirectory name. `local_path` = absolute subdirectory path.
- Runs at **list time** (cheap non-recursive `readdir`); no startup scan or refresh button.

### Identity & merge
- **Stable id** derived deterministically from `local_path` (`uuid5`), so it is identical
  across restarts and list calls — `start`/`stop`/`inject`/harness/runtime-WS all key on it,
  and the injected runtime reports back under the same id.
- List = DB rows (`source=manual`) + discovered (`source=discovered`), **deduped by
  `local_path`** — a manual record for the same path wins; discovery skips it.

### Unified resolver
`get(id)` checks the DB first, else the discovery scan. Every lifecycle endpoint resolves
`id → (local_path, source)` through it, so discovered ids no longer 404.

## API / endpoints

- `GET /devcontainers` and `GET /devcontainers/{id}` return a `status` computed by the live
  resolver and a new `source` field (`manual`/`discovered`). Response shape otherwise
  unchanged. Harness status comes from the in-memory cache (or unknown).
- `DELETE /devcontainers/{id}` — kills + removes the container (`docker rm -f`, resolved by
  the `devcontainer.local_folder` label). For `manual`, also deletes the DB record. For
  `discovered`, only the container is removed — it reappears as `stopped` on the next scan
  (folder is source of truth; no tombstone).
- `POST /devcontainers/{id}/inject-runtime` (**new**) — resolves the container from
  `local_path` and runs the runtime injector. Returns 202; runs in background.
- The automatic `inject()` call is **removed** from `DevcontainerService.start()`.

### CLI adapter additions
- `remove(local_path)` — `docker ps -q --filter label=...` then `docker rm -f <ids>`.
- `running_local_folders() -> set[str]` — one `docker ps` call for the live status resolver.
- The runtime injector gains the ability to resolve `container_id` from `local_path` (same
  label lookup the stop flow uses) for the manual inject path.

## Frontend (detail view + list)

- **Icon control buttons** — replace text Start/Stop with icons; add Inject-Runtime and
  Delete icons. Reuse the existing inline-SVG style (play/stop/trash already exist in the
  list view); add a runtime-inject icon. No new icon library.
- **Delete button** — next to Stop; confirms, then calls `DELETE`. Manual → removed from
  list; discovered → returns to `stopped`.
- **Inject-Runtime button** — calls the new endpoint; shows a pending spinner.
- **Install spinner** — keep the harness install/authenticate button spinning until the SSE
  harness-status update arrives (not on the 202), since the in-memory cache now drives the
  checkmarks. Unknown status (runtime disconnected) renders `?`.
- **Source** — list/detail show whether a devcontainer is `manual` or `discovered`.
- Discovered devcontainers without `created_at`/`updated_at` render those fields as `—`.

## Out of scope
- `delegated_runs` table and its persistence — unused stub, left untouched.
- Filesystem watching / live re-scan beyond per-list-request scanning.
- Recursive discovery; nested devcontainer folders.

## Testing
- Live status resolver: transient precedence over Docker; running/stopped derivation;
  batched Docker query parsing.
- Harness-status cache: push updates, eviction on disconnect, unknown rendering.
- Discovery: scan filters non-`.devcontainer` dirs, dedup by path, stable id, discovery-off
  when config/key absent.
- Endpoints: delete kills+removes container (manual removes row, discovered reappears);
  manual inject resolves container; start no longer auto-injects.
- Frontend: icon buttons wired to correct endpoints; install spinner persists until SSE;
  `?` for unknown harness status.
