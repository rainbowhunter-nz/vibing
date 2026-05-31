# packages/host_runtime — Host Runtime Worker (`vibing-host-runtime`)

Owns the **devcontainer lifecycle** on the host via the official `devcontainer` CLI (ADR-0003 —
never Docker/Podman SDKs directly). A separately-started process that connects to the Control
Plane runtime WebSocket, registers, and serially runs the Commands it receives via the Dev
Container CLI adapter (`devcontainer_cli.py`). The runtime-channel transport (connect, register,
reconnect/backoff, command/event plumbing) lives in `packages/runtime_client`; this package wires
the Dev Container handler onto it. Depends on `packages/protocol` and `packages/runtime_client`.
Read the root `CONTEXT.md`.

Use `uv` only — never hand-edit dependencies in `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_host_runtime/__init__.py` — public surface; re-exports the symbols below.
- `src/vibing_host_runtime/cli.py` — the `vibing-host-runtime` entry point: a Typer `cli` (single flat command, rich-rendered help); `run_worker` builds the `host_runtime_worker` register envelope, wires the adapter + launcher as the command handler, and runs a `RuntimeChannelClient` (from `vibing_runtime_client`); `main` is the console script.
- `src/vibing_host_runtime/client.py` — host-specific config only: `WorkerConfig` plus `DEFAULT_CONTROL_PLANE_URL`, `DEFAULT_DEVCONTAINER_CLI`, and `DEFAULT_AGENT_CONTROL_PLANE_URL` constants. The transport itself lives in `vibing_runtime_client`.
- `src/vibing_host_runtime/devcontainer_cli.py` — `DevcontainerCliAdapter`: maps start/stop to `devcontainer up`/`stop --workspace-folder`, validates `local_path` is a dir, parses `up` JSON into a payload, returns `DevcontainerSuccess`/`DevcontainerFailure` (bounded stderr tail). Injectable `Runner` for tests.
- `src/vibing_host_runtime/agent_launcher.py` — `AgentLauncher`: fires a detached `devcontainer exec` to start `vibing-devcontainer-runtime serve` inside the container after a successful `devcontainer up`. Best-effort: non-zero exit or `FileNotFoundError` → `logger.warning`, never raises. Uses the same `Runner` type as `devcontainer_cli.py`. Injectable runner for tests.
- `src/vibing_host_runtime/runtime.py` — `HOST_COMMAND_TYPES` (devcontainer start/stop), the `HostRuntime` Protocol, and the `HostRuntimeWorker` skeleton (legacy in-process signature; superseded by `client.py`).

## Conventions

- Command/event shapes come from `vibing-protocol` — never redefine them here.
- `HOST_COMMAND_TYPES` must stay a subset of `protocol`'s `CommandType`.
- This package emits events; the Control Plane reducer (`apps/api`) is the one that projects them.
