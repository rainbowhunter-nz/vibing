# Vibing CLI: runtime group + HTTP-client commands

Date: 2026-06-02

## Goal

Make API features testable from the terminal without the frontend, plus a light CLI
refactor. Two pieces:

1. **Refactor** the two long-lived runtime workers under a `runtime` group.
2. **Add** HTTP-client commands that drive the running API for every endpoint.

Constraint: prioritise built-in Typer features; do not re-invent the wheel. Simplicity
first — no aliases, no speculative flags.

## Part 1 — Runtime regrouping

Replace the flat top-level workers with a `runtime` Typer group. No changes inside the
runtime packages; only remount in `src/vibing_cli/__init__.py`.

Before → after:

| Before                         | After                          |
| ------------------------------ | ------------------------------ |
| `vibing host-runtime …`        | `vibing runtime host …`        |
| `vibing devcontainer-runtime …`| `vibing runtime devcontainer …`|

Options are unchanged (they live on each worker's callback):

```
vibing runtime host          [--control-plane-url …] [--devcontainer-cli …] [--agent-control-plane-url …]
vibing runtime devcontainer  --devcontainer-id ID    [--control-plane-url …]
```

Old flat names are removed (no back-compat aliases).

## Part 2 — HTTP-client commands

New subpackage `src/vibing_cli/client/`. Thin `httpx` glue hitting the **running** API
(the server, not the SQLite DB directly). `httpx` is already a dependency.

### Base URL

Resolved from env, mirroring the server `Settings`:

- `VIBING_API_URL` — default `http://localhost:8080`
- `VIBING_API_V1_PREFIX` — default `/api/v1`

Effective base: `{VIBING_API_URL}{VIBING_API_V1_PREFIX}`. No CLI flag for the URL.

> Devcontainer note: the CLI runs inside the devcontainer; the API is published on the
> host. Override with `VIBING_API_URL=http://host.docker.internal:8080` when needed.

### Command tree (resource → endpoint)

Devcontainers (`/devcontainers`):

| Command                                   | HTTP                                   |
| ----------------------------------------- | -------------------------------------- |
| `vibing devcontainer add NAME -d PATH`    | `POST /devcontainers`                  |
| `vibing devcontainer ls`                  | `GET /devcontainers`                   |
| `vibing devcontainer get ID`              | `GET /devcontainers/{id}`              |
| `vibing devcontainer update ID [--name] [--status]` | `PATCH /devcontainers/{id}`  |
| `vibing devcontainer rm ID`               | `DELETE /devcontainers/{id}`           |
| `vibing devcontainer start ID`            | `POST /devcontainers/{id}/start`       |
| `vibing devcontainer stop ID`             | `POST /devcontainers/{id}/stop`        |

`-d` is the short flag for `--local-path`.

Agent sessions — nested `session` sub-app under `devcontainer`
(`/devcontainers/{id}/agent-sessions`):

| Command                                                              | HTTP                                                   |
| ------------------------------------------------------------------- | ------------------------------------------------------ |
| `vibing devcontainer session start ID -p PROMPT`                    | `POST …/agent-sessions`                                |
| `vibing devcontainer session stop ID SESSION_ID`                    | `POST …/agent-sessions/{sid}/stop`                     |
| `vibing devcontainer session input ID SESSION_ID --inbox-event EID --text TEXT` | `POST …/agent-sessions/{sid}/user-input`   |
| `vibing devcontainer session resolve ID SESSION_ID --approval AID --resolution {approved\|rejected}` | `POST …/agent-sessions/{sid}/approval-resolution` |

`--resolution` accepts `approved` | `rejected` (server contract: `Literal["approved","rejected"]`).

Inbox (`/inbox-events`):

| Command                                                                 | HTTP                          |
| ----------------------------------------------------------------------- | ----------------------------- |
| `vibing inbox ls [--status S] [--devcontainer ID] [--session SID]`      | `GET /inbox-events` (query)   |
| `vibing inbox get ID`                                                    | `GET /inbox-events/{id}`      |

Query params map: `--status`→`status`, `--devcontainer`→`devcontainer_id`,
`--session`→`agent_session_id`. Omitted flags are not sent.

Approvals (`/approval-requests`):

| Command                     | HTTP                              |
| --------------------------- | --------------------------------- |
| `vibing approval ls`        | `GET /approval-requests`          |
| `vibing approval get ID`    | `GET /approval-requests/{id}`     |

System reads (unprefixed under `/api/v1`):

| Command                     | HTTP                  |
| --------------------------- | --------------------- |
| `vibing system status`      | `GET /status`         |
| `vibing system diagnostics` | `GET /diagnostics`    |
| `vibing system config`      | `GET /config`         |
| `vibing system settings`    | `GET /settings`       |
| `vibing system health`      | `GET /health`         |

### Shared internals

- `client/http.py` — resolve base URL from env; `request(method, path, *, json=None, params=None)`
  wrapper over `httpx`. Returns parsed JSON for 2xx. Error handling:
  - `httpx.ConnectError` → red `Cannot reach API at <base-url>`; `raise typer.Exit(1)`.
  - non-2xx → parse the standard envelope `{"error": {"code","message","details"}}` and
    render `code` + `message` in red; `raise typer.Exit(1)`. Fall back to raw body if the
    envelope is absent.
- `client/render.py` — generic rendering of returned JSON (no coupling to server schemas):
  - list payloads (`{"items": [...]}` or a JSON array) → rich `Table`, columns from keys.
  - single object → rich key/value table.
  - shared `JsonOption = Annotated[bool, typer.Option("--json", help="Raw JSON output")]`;
    when set, print `json.dumps(data, indent=2)` and skip rich rendering.
- One Typer app per resource module: `devcontainers.py` (with nested `session` sub-app),
  `inbox.py`, `approvals.py`, `system.py`. Mounted in `__init__.py`.

Read commands accept `--json`. Mutating commands print a short rich confirmation and also
accept `--json` to dump the response body.

### Output examples

`vibing devcontainer ls` (default):

```
        Devcontainers
┏━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃ id     ┃ name     ┃ status  ┃
┡━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│ dc_01  │ sandbox  │ running │
└────────┴──────────┴─────────┘
```

`vibing devcontainer get dc_01 --json` → raw JSON body.

## Files

New / changed:

- `src/vibing_cli/__init__.py` — mount `runtime` group + 4 client groups.
- `src/vibing_cli/client/__init__.py` — new (empty/package marker).
- `src/vibing_cli/client/http.py` — new.
- `src/vibing_cli/client/render.py` — new.
- `src/vibing_cli/client/devcontainers.py` — new (devcontainer + nested session apps).
- `src/vibing_cli/client/inbox.py` — new.
- `src/vibing_cli/client/approvals.py` — new.
- `src/vibing_cli/client/system.py` — new.
- `src/vibing_cli/CLAUDE.md` — update command list.
- `tests/cli/` — new tests.

## Testing

`tests/cli/` with Typer `CliRunner` + `httpx.MockTransport` (no new deps):

- Wiring: `vibing runtime host --help` and `vibing runtime devcontainer --help` work; old
  flat `vibing host-runtime` / `vibing devcontainer-runtime` are gone.
- Client happy paths: each command issues the right method/path/body/params against the
  mock transport and renders output; `--json` returns raw body.
- Errors: `ConnectError` and a 404 envelope both exit non-zero with a rendered message.

Mock transport is injected by pointing `client/http.py` at an `httpx.Client` whose
`transport` is overridable in tests (e.g. a module-level client factory the tests patch).

## Checks (must pass)

```
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest -q
```

## Out of scope

- WebSocket/runtime-event streaming from the client CLI.
- Back-compat aliases for the old flat runtime command names.
- Auth (API is local/unauthenticated).
