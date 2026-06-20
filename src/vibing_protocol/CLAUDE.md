# vibing_protocol

Shared typed contract between API, runtimes, and frontend docs.

## Files

- `commands.py`: `CommandType` StrEnum (`AUTHENTICATE_HARNESS`, `INSTALL_HARNESS`) + `Command` model.
- `messages.py`: WebSocket envelopes — `RegisterEnvelope`, `CommandEnvelope`, `HarnessStatusEnvelope`/`HarnessStatusItem`, `DelegatedRunsEnvelope`/`DelegatedRunItem`.
- `channel.py`: wire codec — `encode(envelope)`/`decode(raw)` shared by both ends of the runtime channel.

## Context

- `CommandType` is a `StrEnum`; values = wire strings via `auto()`. Compare with members, not raw strings.
- Both the Control Plane and the Devcontainer Runtime serialize/parse envelopes through `channel.encode`/`channel.decode`.
- Keep dependencies light: Pydantic + stdlib.
