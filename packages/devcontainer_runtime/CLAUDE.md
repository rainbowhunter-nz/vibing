# packages/devcontainer_runtime — Devcontainer Runtime Agent (`vibing-devcontainer-runtime`)

Runs **inside** the container and owns the **agent-session lifecycle** (eventually: launching
Claude Code, PTY, streaming output, approval detection). Receives devcontainer-side Commands
from the Control Plane and emits RuntimeEvents back. **Skeleton only today** — `handle()` raises
`NotImplementedError`; no process launches, no PTY, no I/O; transport deferred (ADR-0003).
Depends on `packages/protocol`. Read the root `CONTEXT.md`.

Use `uv` only — never hand-edit `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_devcontainer_runtime/__init__.py` — public surface; re-exports the symbols below.
- `src/vibing_devcontainer_runtime/runtime.py` — `DEVCONTAINER_COMMAND_TYPES` (agent-session start/stop, send_user_input, resolve_approval), the `DevcontainerRuntime` Protocol, and the `DevcontainerRuntimeAgent` skeleton.

## Conventions

- Command/event shapes come from `vibing-protocol` — never redefine them here.
- `DEVCONTAINER_COMMAND_TYPES` must stay a subset of `protocol`'s `CommandType`.
- This package emits events; the Control Plane reducer (`apps/api`) is the one that projects them.
