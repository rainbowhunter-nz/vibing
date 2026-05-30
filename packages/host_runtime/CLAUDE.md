# packages/host_runtime — Host Runtime Worker (`vibing-host-runtime`)

Owns the **devcontainer lifecycle** on the host via the official `devcontainer` CLI (ADR-0003 —
never Docker/Podman SDKs directly). A separately-started process that connects to the Control
Plane runtime WebSocket, registers, and serially runs the Commands it receives via the Dev
Container CLI adapter (`devcontainer_cli.py`). Depends on `packages/protocol`. Read the root
`CONTEXT.md`.

Use `uv` only — never hand-edit dependencies in `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_host_runtime/__init__.py` — public surface; re-exports the symbols below.
- `src/vibing_host_runtime/cli.py` — the `vibing-host-runtime` entry point: a Typer `cli` (single flat command, rich-rendered help); `run_worker` wires the adapter as the command handler and runs the loop; `main` is the console script.
- `src/vibing_host_runtime/client.py` — `WorkerConfig`, `Backoff`, and `HostRuntimeClient` (reconnect loop + in-memory FIFO command queue). Logging uses `logzero` (startup, registration, inbound commands, outbound events, reconnects).
- `src/vibing_host_runtime/devcontainer_cli.py` — `DevcontainerCliAdapter`: maps start/stop to `devcontainer up`/`stop --workspace-folder`, validates `local_path` is a dir, parses `up` JSON into a payload, returns `DevcontainerSuccess`/`DevcontainerFailure` (bounded stderr tail). Injectable `Runner` for tests.
- `src/vibing_host_runtime/runtime.py` — `HOST_COMMAND_TYPES` (devcontainer start/stop), the `HostRuntime` Protocol, and the `HostRuntimeWorker` skeleton (legacy in-process signature; superseded by `client.py`).

## Conventions

- Command/event shapes come from `vibing-protocol` — never redefine them here.
- `HOST_COMMAND_TYPES` must stay a subset of `protocol`'s `CommandType`.
- This package emits events; the Control Plane reducer (`apps/api`) is the one that projects them.
