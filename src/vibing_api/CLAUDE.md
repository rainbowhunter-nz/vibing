# vibing_api

FastAPI control plane. Owns API routes, SQLite state, runtime WS intake, projections.

## Files

- `main.py`: app factory, router mounting, static frontend serving.
- `api/routes/`: HTTP + WebSocket routes.
- `api/schemas/`: API response/request models.
- `core/runtime_channel.py`: runtime WS managers, command send, event persistence.
- `core/session_stream.py`: per-session live turn-delta fan-out with in-memory replay buffer
  (ADR-0010, VIB-111). SEPARATE from the invalidation Broadcaster. Keyed by agent_session_id;
  each publish appends (event_id, data) to a per-run buffer and fans out to live subscribers.
  `subscribe(last_event_id)` atomically snapshots the buffer + registers the queue so no item
  is missed. `begin_run`/`end_run` (also auto-detected from the delta `kind`) manage the
  lifecycle. `routes/session_stream.py` serves `GET .../agent-sessions/{id}/stream` (SSE) and
  reads the `Last-Event-ID` header for reconnect. The agent WS `turn_delta` branch relays.
- `core/reducer.py`: project runtime events into read models.
- `core/database.py`, `core/schema.py`: SQLite setup and schema.
- `repositories/`: SQL only. Callers commit transactions.
- `cli/dev.py`: dev helpers, mounted as `vibing dev ...`.

## Context

- `/runtime/ws`: one host runtime worker.
- `/runtime/agent/ws`: one agent per devcontainer id.
- Tests: `tests/api`.
