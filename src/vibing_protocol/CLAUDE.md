# vibing_protocol

Shared typed contract between API, runtimes, and frontend docs.

## Files

- `commands.py`: `CommandType` StrEnum (only `AUTHENTICATE_HARNESS`) + `Command` model.
- `messages.py`: WebSocket envelopes — `RegisterEnvelope`, `CommandEnvelope`, `HarnessStatusEnvelope`/`HarnessStatusItem`.

## Context

- `CommandType` is a `StrEnum`; values = wire strings via `auto()`. Compare with members, not raw strings.
- Keep dependencies light: Pydantic + stdlib.
