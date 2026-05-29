# packages/protocol — shared message shapes (`vibing-protocol`)

The wire vocabulary shared by the Control Plane and both runtimes: allowed Command/RuntimeEvent
types and their typed Pydantic shapes. **No dispatch, no persistence, no I/O** — consumers own
those. This is the lowest dependency in the workspace (`apps/api` and both runtime packages
depend on it; it depends on nothing internal). Read the root `CONTEXT.md` for domain terms.

Use `uv` only — never hand-edit `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_protocol/__init__.py` — public surface; re-exports every type/constant below.
- `src/vibing_protocol/commands.py` — `CommandType` Literal + `COMMAND_TYPES` frozenset + `Command` model (control-plane request to a runtime).
- `src/vibing_protocol/runtime_events.py` — `EventType` / `RuntimeEventSource` Literals + their frozensets + `RuntimeEvent` model + `InvalidRuntimeEventError`.

## Conventions

- Vocabularies are `Literal`s; the matching frozenset is derived via `get_args` — add a value in one place.
- Changing a type or field here ripples to `apps/api` (reducer, repositories, schema) and the runtimes — grep before editing.
