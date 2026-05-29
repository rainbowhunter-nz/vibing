# packages/host_runtime — Host Runtime Worker (`vibing-host-runtime`)

Owns the **devcontainer lifecycle** on the host (eventually: Dev Container CLI, Docker/Podman).
Receives host-side Commands from the Control Plane and emits RuntimeEvents back. **Skeleton
only today** — `handle()` raises `NotImplementedError`; the TCP/IP transport is deferred (ADR-0003).
No Docker/Podman/CLI calls yet. Depends on `packages/protocol`. Read the root `CONTEXT.md`.

Use `uv` only — never hand-edit `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_host_runtime/__init__.py` — public surface; re-exports the symbols below.
- `src/vibing_host_runtime/runtime.py` — `HOST_COMMAND_TYPES` (devcontainer start/stop/restart), the `HostRuntime` Protocol, and the `HostRuntimeWorker` skeleton.

## Conventions

- Command/event shapes come from `vibing-protocol` — never redefine them here.
- `HOST_COMMAND_TYPES` must stay a subset of `protocol`'s `CommandType`.
- This package emits events; the Control Plane reducer (`apps/api`) is the one that projects them.
