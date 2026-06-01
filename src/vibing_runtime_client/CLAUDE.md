# vibing_runtime_client

Shared runtime WebSocket client. Used by host worker and devcontainer agent.

## Files

- `client.py`: reconnect loop, registration send, command receive queue, event emit envelope.
- `__init__.py`: public exports.

## Context

- Does not know command semantics.
- Callers pass `RegisterEnvelope` and command handler.
- Commands run serially from an in-memory queue.
- No replay after disconnect.
- Tests: `tests/runtime_client`.
