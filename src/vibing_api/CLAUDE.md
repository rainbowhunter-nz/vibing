# vibing_api

FastAPI control plane. Owns API routes, SQLite state, runtime WS intake, projections.

## Files

- `main.py`: app factory, router mounting, static frontend serving.
- `api/routes/`: HTTP + WebSocket routes.
- `api/schemas/`: API response/request models.
- `core/runtime_channel.py`: runtime WS managers, command send, event persistence.
- `core/reducer.py`: project runtime events into read models.
- `core/database.py`, `core/schema.py`: SQLite setup and schema.
- `repositories/`: SQL only. Callers commit transactions.
- `cli/dev.py`: dev helpers, mounted as `vibing dev ...`.

## Context

- `/runtime/ws`: one host runtime worker.
- `/runtime/agent/ws`: one agent per devcontainer id.
- Tests: `tests/api`.
