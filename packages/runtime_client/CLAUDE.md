# packages/runtime_client — Shared Runtime-Channel Client (`vibing-runtime-client`)

Shared WebSocket transport for Vibing runtimes (host and devcontainer). `RuntimeChannelClient`
owns: connect, bounded exponential-backoff reconnect loop, sending the register envelope, parsing
inbound `command` envelopes, and an `emit(RuntimeEvent)` closure. Construction takes the Control
Plane URL, the register envelope to send, and a command `handler`. Depends on `packages/protocol`
only. Read the root `CONTEXT.md`.

Use `uv` only — never hand-edit `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_runtime_client/__init__.py` — public surface; re-exports symbols below.
- `src/vibing_runtime_client/client.py` — `Backoff`, `RuntimeChannelClient` (reconnect loop, FIFO command queue, `_run_session`, `_consume`, `_make_emit`), type aliases `EmitFn`/`CommandHandler`/`ConnectFn`/`SleepFn`, and module helper `_parse_command`.

## Conventions

- Depends on `vibing-protocol` only — never import from `vibing_host_runtime` or `apps/api`.
- `connect`/`sleep`/`backoff` are injectable for deterministic tests.
