# packages/host_runtime — Host Runtime Worker (`vibing-host-runtime`)

Owns the **devcontainer lifecycle** on the host via the official `devcontainer` CLI (ADR-0003 —
never Docker/Podman SDKs directly). A separately-started process that connects to the Control
Plane runtime WebSocket, registers, and serially runs the Commands it receives. The Dev Container
CLI adapter (`devcontainer_cli.py`) exists; wiring it as the queue's command `handler` is still a
no-op placeholder (VIB-27). Depends on `packages/protocol`. Read the root `CONTEXT.md`.

Use `uv` only — never hand-edit dependencies in `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_host_runtime/__init__.py` — public surface; re-exports the symbols below.
- `src/vibing_host_runtime/client.py` — the `vibing-host-runtime` process: `parse_args`/`WorkerConfig`, `Backoff`, and `HostRuntimeClient` (reconnect loop + in-memory FIFO command queue), plus `main`.
- `src/vibing_host_runtime/devcontainer_cli.py` — `DevcontainerCliAdapter`: maps start/stop to `devcontainer up`/`stop --workspace-folder`, validates `local_path` is a dir, parses `up` JSON into a payload, returns `DevcontainerSuccess`/`DevcontainerFailure` (bounded stderr tail). Injectable `Runner` for tests.
- `src/vibing_host_runtime/runtime.py` — `HOST_COMMAND_TYPES` (devcontainer start/stop), the `HostRuntime` Protocol, and the `HostRuntimeWorker` skeleton (legacy in-process signature; superseded by `client.py`).

## Conventions

- Command/event shapes come from `vibing-protocol` — never redefine them here.
- `HOST_COMMAND_TYPES` must stay a subset of `protocol`'s `CommandType`.
- This package emits events; the Control Plane reducer (`apps/api`) is the one that projects them.
