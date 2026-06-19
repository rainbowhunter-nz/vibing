# Foundation API — examples

Short request/response examples for the foundation HTTP surface, so frontend and
backend stay aligned. Field names are canonical (see [`CONTEXT.md`](../CONTEXT.md));
schemas live in `src/vibing_api/api/`.

All routes are served under `/api/v1` (`VIBING_API_V1_PREFIX`). Examples below use
that full path. Bodies are JSON; the error envelope is shared (see [Errors](#errors)).

> **Metadata APIs vs. runtime APIs.** Most routes here are the **metadata**
> surface: read-only config/health plus Devcontainer CRUD. Lifecycle routes
> (`start`/`stop`) return `202 Accepted`; the Control Plane runs the Dev Container
> CLI in a background task and writes state directly as it progresses — the browser
> sees changes via SSE invalidation. The forward-looking fields below —
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
records metadata only. Use the lifecycle routes below to trigger start/stop via the
Control Plane.

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

Requires the Devcontainer to be in `created`, `stopped`, or `error`. The Control
Plane runs `devcontainer up` in a background task, writing status (`starting →
running`, or `error`) directly as it progresses. After a successful up it injects
and launches the Devcontainer Runtime. Returns the current Devcontainer read model.

### `POST /api/v1/devcontainers/{id}/stop` → `202`

Requires the Devcontainer to be in `running` or `error`. The Control Plane stops
the container, writing status (`stopping → stopped`, or `error`) directly. Returns
the current Devcontainer read model.

## Harnesses

### `POST /api/v1/devcontainers/{id}/harnesses/{harness}/authenticate` → `202`

Requires the Devcontainer to be `running` and its Devcontainer Runtime connected.
Sends an `authenticate_harness` Command carrying the stored credentials. The
runtime installs and authenticates the harness, then reports updated Harness Status.

`harness` is one of `codex`, `cursor` (managed harnesses).

### `GET /api/v1/devcontainers/{id}/harnesses`

Returns current Harness Status for all managed harnesses in the Devcontainer.

```json
{
  "items": [
    { "harness": "codex", "installed": true, "authenticated": false },
    { "harness": "cursor", "installed": false, "authenticated": false }
  ]
}
```

## Sample data

Local-dev fixtures, not an HTTP API — a Typer CLI that seeds curated rows for UI
validation. Every row's `id` is prefixed `sample-` and every name starts with
`[sample] `, so fixtures are visible in the UI and removed in one pass without
touching real rows.

```
$ uv run vibing dev sample_data seed
Seeded rows.

$ uv run vibing dev sample_data status
        Sample data
┏━━━━━━━━━━━━━━━┳━━━━━━┓
┃ Table         ┃ Rows ┃
┡━━━━━━━━━━━━━━━╇━━━━━━┩
│ devcontainers │    3 │
└───────────────┴──────┘

$ uv run vibing dev sample_data reset
Removed sample rows.
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
