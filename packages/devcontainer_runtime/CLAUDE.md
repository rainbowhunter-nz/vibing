# packages/devcontainer_runtime — Devcontainer Runtime Agent (`vibing-devcontainer-runtime`)

Runs **inside** the container and owns the **agent-session lifecycle** (eventually: launching
Claude Code, PTY, streaming output, approval detection). Receives devcontainer-side Commands
from the Control Plane and emits RuntimeEvents back. Has a `serve` CLI that connects to
`/runtime/agent/ws`, registers as `devcontainer_runtime_agent` with a `devcontainer_id`, and
idles awaiting Commands (session logic deferred to VIB-32). Depends on `packages/protocol`
and `packages/runtime_client`. Read the root `CONTEXT.md`.

Use `uv` only — never hand-edit `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_devcontainer_runtime/__init__.py` — public surface; re-exports the symbols below.
- `src/vibing_devcontainer_runtime/cli.py` — `vibing-devcontainer-runtime` entry point: Typer `cli`, `serve` command with `--control-plane-url` and `--devcontainer-id` options; builds `RegisterEnvelope(source="devcontainer_runtime_agent", devcontainer_id=...)` and runs `RuntimeChannelClient`. Default URL: `ws://host.docker.internal:8000/api/v1/runtime/agent/ws`.
- `src/vibing_devcontainer_runtime/runtime.py` — `DEVCONTAINER_COMMAND_TYPES` (agent-session start/stop, send_user_input, resolve_approval), the `DevcontainerRuntime` Protocol, and the `DevcontainerRuntimeAgent` skeleton.

## Conventions

- Command/event shapes come from `vibing-protocol` — never redefine them here.
- `DEVCONTAINER_COMMAND_TYPES` must stay a subset of `protocol`'s `CommandType`.
- This package emits events; the Control Plane reducer (`apps/api`) is the one that projects them.
