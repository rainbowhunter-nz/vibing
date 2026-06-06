# vibing_protocol

Shared typed contract between API, runtimes, and frontend docs.

## Files

- `commands.py`: `CommandType` StrEnum + `Command` model.
- `runtime_events.py`: `EventType`/`RuntimeEventSource` StrEnums + `RuntimeEvent` model.
- `messages.py`: WebSocket register/command/event envelopes + transcript request/reply
  (`TranscriptRequestEnvelope`/`TranscriptResponseEnvelope`) and normalized turn/block
  models (`TranscriptTurn`, `TextBlock`/`ToolUseBlock`, discriminated on `kind`).

## Context

- Vocabularies are `StrEnum`s (values = wire strings via `auto()`). Compare and construct with members, not raw strings.
- When adding a command/event: add the enum member, then update handlers, reducer, tests, docs.
- Keep dependencies light: Pydantic + stdlib.