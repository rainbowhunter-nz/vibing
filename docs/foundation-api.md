# Foundation API — examples

Short request/response examples for the foundation HTTP surface, so frontend and
backend stay aligned. Field names are canonical (see [`CONTEXT.md`](../CONTEXT.md));
schemas live in `src/vibing_api/api/`.

All routes are served under `/api/v1` (`VIBING_API_V1_PREFIX`). Examples below use
that full path. Bodies are JSON; the error envelope is shared (see [Errors](#errors)).

> **Metadata APIs vs. runtime APIs.** Most routes here are the **metadata**
> surface: read-only config/health plus Devcontainer CRUD. Lifecycle routes
> record user intent by sending Commands to connected runtimes; read-model state
> still changes only after Runtime Events are emitted back and projected. Session
> Output streaming remains deferred. The forward-looking fields below —
> `runtime` in `/settings`, and the `docker`/`podman`/`devcontainer_cli`/
> `claude_code` diagnostics — exist now but report `null`/`unknown` until
> detection lands in a later ticket.

## Health & status

### `GET /api/v1/health`

Liveness probe. Static, no I/O.

```json
{ "status": "ok", "service": "vibing-api" }
```

### `GET /api/v1/status`

Health plus the running package `version` (from package metadata; `0.0.0` if unknown).

```json
{ "status": "ok", "service": "vibing-api", "version": "0.1.0" }
```

## Config & settings

### `GET /api/v1/config`

Static app config the frontend needs at boot.

```json
{ "app_name": "vibing-api", "api_v1_prefix": "/api/v1" }
```

### `GET /api/v1/settings`

Backend address plus runtime detection. `runtime` fields are `null` (unknown) until
detection is implemented — a future-runtime placeholder, not a live result.

```json
{
  "backend_host": "0.0.0.0",
  "backend_port": 8080,
  "runtime": {
    "docker": null,
    "podman": null,
    "devcontainer_cli": null,
    "claude_code": null
  }
}
```

## Diagnostics

### `GET /api/v1/diagnostics`

Prerequisite checks. Each check has `status` of `ok` | `fail` | `unknown`. Only
`backend` and `sqlite` run today; the rest are `unknown` placeholders for runtime
detection.

```json
{
  "checks": [
    { "id": "backend", "label": "Backend", "status": "ok", "message": "API responding" },
    { "id": "sqlite", "label": "SQLite", "status": "ok", "message": "schema_version=2" },
    { "id": "devcontainer_cli", "label": "Dev Container CLI", "status": "unknown", "message": "Not implemented yet" },
    { "id": "docker", "label": "Docker", "status": "unknown", "message": "Not implemented yet" },
    { "id": "podman", "label": "Podman", "status": "unknown", "message": "Not implemented yet" },
    { "id": "claude_code", "label": "Claude Code", "status": "unknown", "message": "Not implemented yet" }
  ]
}
```

A failed check carries the reason in `message`:

```json
{ "id": "sqlite", "label": "SQLite", "status": "fail", "message": "schema_version missing from app_meta" }
```

## Devcontainers

The Devcontainer is the central entity (the domain term for what a user calls a
"workspace"). A Devcontainer is bound to one `local_path` ([ADR-0001](adr/0001-devcontainer-source-is-a-single-local-path.md)).
`status` is one of `created` | `starting` | `running` | `stopping` | `stopped` | `error`.

Creating a Devcontainer does **not** start a container, and `PATCH`-ing `status`
records metadata only. Use the lifecycle routes below to send start/stop Commands
to a connected Host Runtime Worker.

### `POST /api/v1/devcontainers` → `201`

Request:

```json
{ "name": "vibing-web", "local_path": "/home/me/projects/vibing-web" }
```

Response:

```json
{
  "id": "b3f1c2a4-5d6e-4f80-9a1b-2c3d4e5f6a7b",
  "name": "vibing-web",
  "local_path": "/home/me/projects/vibing-web",
  "status": "created",
  "created_at": "2026-05-29T04:00:00+00:00",
  "updated_at": "2026-05-29T04:00:00+00:00"
}
```

### `GET /api/v1/devcontainers`

```json
{
  "items": [
    {
      "id": "b3f1c2a4-5d6e-4f80-9a1b-2c3d4e5f6a7b",
      "name": "vibing-web",
      "local_path": "/home/me/projects/vibing-web",
      "status": "running",
      "created_at": "2026-05-29T04:00:00+00:00",
      "updated_at": "2026-05-29T04:05:12+00:00"
    }
  ]
}
```

An empty list is `{ "items": [] }`.

### `GET /api/v1/devcontainers/{id}`

Returns one `Devcontainer` (same shape as the array item above), or `404` if unknown.

### `PATCH /api/v1/devcontainers/{id}`

Partial update; send only the fields you change.

Request:

```json
{ "name": "vibing-web-renamed" }
```

Response: the full updated `Devcontainer`, or `404` if unknown.

### `DELETE /api/v1/devcontainers/{id}` → `204`

Empty body on success; `404` if unknown.

### `POST /api/v1/devcontainers/{id}/start` → `202`

Requires a connected Host Runtime Worker (`uv run vibing host-runtime`) and a
Devcontainer currently in `created`, `stopped`, or `error`. Returns the current
Devcontainer read model unchanged; `starting`/`running`/`error` arrives later via
Runtime Events.

### `POST /api/v1/devcontainers/{id}/stop` → `202`

Requires a connected Host Runtime Worker and a Devcontainer currently in
`running` or `error`. Returns the current Devcontainer read model unchanged;
`stopping`/`stopped`/`error` arrives later via Runtime Events.

### `POST /api/v1/devcontainers/{id}/agent-sessions` → `202`

Requires the Devcontainer to be `running` and its Devcontainer Runtime Agent to
be connected. Sends `start_agent_session` to that agent and returns the created
Agent Session read model.

Request:

```json
{ "prompt": "Implement the failing test" }
```

### `POST /api/v1/devcontainers/{id}/agent-sessions/{session_id}/resume` → `202`

Continues a rested conversation in place (ADR-0008). Requires the session to be in
a resting state (`completed`/`failed`/`stopped`), the Devcontainer `running`, its
agent connected, and no other session active (else `409`
`AGENT_SESSION_NOT_RESTING` / `INVALID_DEVCONTAINER_STATE` / `RUNTIME_UNAVAILABLE`
/ `AGENT_SESSION_ACTIVE`). Optimistically sets the session to `starting`, sends
`resume_agent_session` to the agent (which runs `claude --resume <id>`), and
returns the updated Agent Session. Reuses the existing lifecycle events.

Request:

```json
{ "prompt": "Now run the tests" }
```

### `POST /api/v1/devcontainers/{id}/agent-sessions/{session_id}/stop` → `202`

Requires the Agent Session to be active and the Devcontainer Runtime Agent to be
connected. Sends `stop_agent_session` to that agent and returns the current Agent
Session read model unchanged; final status arrives later via Runtime Events.

## Sample data

Local-dev fixtures, not an HTTP API — a Typer CLI that seeds curated rows for UI
validation. Every row's `id` is prefixed `sample-` and every name starts with
`[sample] `, so fixtures are visible in the UI and removed in one pass without
touching real rows.

```
$ uv run vibing dev sample_data seed
Seeded 12 rows.

$ uv run vibing dev sample_data status
        Sample data
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃ Table             ┃ Rows ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│ devcontainers     │    3 │
│ agent_sessions    │    3 │
│ approval_requests │    2 │
│ inbox_events      │    4 │
└───────────────────┴──────┘

$ uv run vibing dev sample_data reset
Removed 12 sample rows.
```

A seeded Devcontainer row, as returned by `GET /api/v1/devcontainers`:

```json
{
  "id": "sample-dc-web",
  "name": "[sample] vibing-web",
  "local_path": "/sample/projects/vibing-web",
  "status": "running",
  "created_at": "2026-01-01T12:00:00+00:00",
  "updated_at": "2026-01-01T12:00:00+00:00"
}
```

## Errors

All errors share one envelope: an `error` object with a stable `code`, a
human-readable `message`, and optional `details`.

```json
{ "error": { "code": "string", "message": "string", "details": null } }
```

`404` — unknown Devcontainer (`DEVCONTAINER_NOT_FOUND`):

```json
{
  "error": {
    "code": "DEVCONTAINER_NOT_FOUND",
    "message": "Devcontainer not found: b3f1c2a4-5d6e-4f80-9a1b-2c3d4e5f6a7b",
    "details": null
  }
}
```

`422` — request validation failed (`VALIDATION_ERROR`); `details` lists the offending
fields:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      { "type": "string_too_short", "loc": ["body", "name"], "msg": "String should have at least 1 character", "input": "", "ctx": { "min_length": "1" } }
    ]
  }
}
```

Other codes: `HTTP_ERROR` (unmapped 4xx, e.g. an unknown route) and
`INTERNAL_SERVER_ERROR` (5xx).
