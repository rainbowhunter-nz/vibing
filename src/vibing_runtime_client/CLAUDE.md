# vibing_runtime_client

Shared runtime WebSocket client. Used by host worker and devcontainer agent.

## Files

- `client.py`: reconnect loop (private bounded backoff), registration send, command receive
  queue, generic outbound `send` (any envelope), generic request/reply dispatch
  (`on_request(message_type, respond)`, ADR-0009). `run_blocking()` is the sync CLI entry
  point (SIGTERM/SIGINT -> clean stop).
- `__init__.py`: public exports (`RuntimeChannelClient`, handler types).
- `README.md`: API usage + minimal example.

## Context

- Knows no domain message types beyond Command; callers pass `RegisterEnvelope` and a
  `CommandHandler(command, send)`, and register request responders per message type.
- Commands run serially from an in-memory queue.
- No replay after disconnect.
- Connection factory/backoff are implementation details; tests monkeypatch them on the module.
- Tests: `tests/runtime_client`.
