# Discovered devcontainers are persisted via a startup filesystem sync

Previously, discovered devcontainers (folders under `devcontainers_dir` that contain `.devcontainer/`) were emitted as virtual `DiscoveredDevcontainer` objects — never persisted — and merged with manual DB rows at read time via `DevcontainerCatalog`. The manual/discovered distinction was exposed as a `source` field (`manual` | `discovered`) on API responses.

We remove the virtual/catalog model entirely: at startup, `core/devcontainer_sync.py` upserts every scanned folder as an ordinary DB row and evicts any row whose folder no longer has `.devcontainer/`. After sync, all devcontainer resolution is a plain DB read via `core/devcontainer_store.py` (`DevcontainerStore`). There is no `source` field, no manual-vs-discovered distinction, and no read-time merge.

## Why

- **Single resolution path.** The catalog merge existed only to make discovered ids routable without a DB row. Persisting on startup removes the need for a virtual layer entirely — one code path for list/get/lifecycle.
- **`name` ownership.** Upsert is set-once for `name`: the startup scan supplies the folder name as the initial value; user renames via PATCH are preserved on subsequent syncs.
- **Simpler DELETE.** Previously DELETE had asymmetric behavior (removed manual rows; discovered would reappear). Now DELETE always removes the row; if the folder still exists it will reappear on next restart or POST.
- **POST is idempotent.** `POST /devcontainers` upserts by `local_path`, so it is safe to call for an already-synced folder.

## Consequences

- **New folders surface after restart or POST**, not live. Users expecting immediate discovery must restart vibing or POST manually.
- **Stale rows are evicted on startup.** If a folder's `.devcontainer/` is removed, the row (whether originally manual or discovered) is deleted at next startup and its live-state caches are cleared. This can orphan a still-running container — killable via `docker rm -f`. Accepted: keeping the sync Docker-free (no `docker ps` call in sync) is worth the edge-case manual cleanup.
- **`source` field removed from all API responses.** No downstream impact within the project.
- `core/catalog.py` deleted; `core/discovery.py` remains but is now the scanner feeding the startup sync, not a virtual-id generator for a merge.

Re-scopes the discovered-devcontainer behavior near [ADR-0001](0001-devcontainer-source-is-a-single-local-path.md). ADR-0001 remains valid — source of a devcontainer is still a single `local_path` column.

Status: accepted
