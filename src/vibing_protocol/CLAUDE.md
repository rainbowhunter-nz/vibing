# vibing_protocol

Shared typed contract between API, runtimes, and frontend docs.

## Files

- `commands.py`: `CommandType` StrEnum + `Command` model. New: `AUTHENTICATE_HARNESS`.
- `runtime_events.py`: `EventType`/`RuntimeEventSource` StrEnums + `RuntimeEvent` model. New: `HARNESS_STATUS`, `DELEGATED_RUN_STARTED`/`COMPLETED`/`FAILED` (payload carries `delegated_run_id`, `harness`).
- `messages.py`: WebSocket register/command/event envelopes + transcript request/reply
  (`TranscriptRequestEnvelope`/`TranscriptResponseEnvelope`) and normalized turn/block
  models (`TranscriptTurn` with a stable `id`, `TextBlock`/`ToolUseBlock`, discriminated on
  `kind`). Live Session Stream (ADR-0010): `TurnDeltaEnvelope` carrying a `TurnDelta`
  (`RunStartedDelta`/`TextDelta`/`RunEndedDelta`, discriminated on `kind`; text-only slice).

## Context

- Vocabularies are `StrEnum`s (values = wire strings via `auto()`). Compare and construct with members, not raw strings.
- When adding a command/event: add the enum member, then update handlers, reducer, tests, docs.
- Keep dependencies light: Pydantic + stdlib.