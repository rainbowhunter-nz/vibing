# vibing_protocol

Shared typed contract between API, runtimes, and frontend docs.

## Files

- `commands.py`: control-plane command literals and model.
- `runtime_events.py`: runtime event/source literals and model.
- `messages.py`: WebSocket register/command/event envelopes.

## Context

- Keep literals explicit.
- When adding a command/event: update handlers, reducer, tests, docs.
- Keep dependencies light: Pydantic + stdlib.