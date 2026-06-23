# Vibing

A local control panel for running coding harnesses across isolated devcontainers. It spins
containers up and down, manages harness credentials once on the host, and runs an in-container
companion that reduces the friction of using coding harnesses (install, auth, MCP delegation).
This glossary is the canonical language for the domain — code, docs, and conversation should use
these terms.

## Language

**Devcontainer**:
The central persistent entity: one isolated development container bound to exactly one local
folder path. Owns its harness status and credentials wiring. Exists even when not running
(`created`/`stopped`); "running" means the container is up. Everything else hangs off it.
_Avoid_: Workspace, project, environment, repo

**Control Plane**:
The backend (FastAPI + SQLite) and the only hub. It holds all metadata, drives the Devcontainer
lifecycle **directly** by shelling out to the Dev Container CLI in-process (no separate worker),
stores Coding Harness credentials, sends Commands to Devcontainer Runtimes, and consumes the
Harness Status they report. It is the only writer of derived state, which it mutates directly —
there is no event log. The frontend is a separate client over `/api/v1` HTTP and is *not* part of
the Control Plane.
_Avoid_: server, orchestrator, host runtime worker; do not include the frontend

**Devcontainer Runtime**:
The in-container companion process, one per running Devcontainer. Its purpose is to add capability
on top of Coding Harnesses inside an ephemeral container. It hosts an MCP server the main harness
calls to start Delegated Runs (and locally checks managed-harness status for that server's
`list_harnesses`). Harness install/authenticate/status-for-display is **not** its job — the
Control Plane owns that directly via `devcontainer exec` (ADR-0019). Designed to grow more
capabilities (e.g. skills management). Connects out to the Control Plane over a WebSocket, routed
by `devcontainer_id`; the channel is **outbound-only** (it receives no Commands).
_Avoid_: agent, runtime agent, worker, daemon; never call it "the agent" (the harness is the agent)

**Coding Harness**:
The installable CLI program that runs a coding agent inside a Devcontainer — Claude Code (`claude`),
Codex CLI (`codex`), Cursor CLI (`cursor-agent`). Two queryable states: **installed** (binary
present) and **authenticated** (working credentials). A model is a *parameter* passed when spawning,
not part of the harness identity. Two roles: the **main harness** is the one a human drives directly
inside the Devcontainer (Claude Code today) — it is the *client* of the MCP server and is never
managed by the runtime; a **managed harness** is one the Devcontainer Runtime checks, installs,
authenticates, and spawns on the main harness's behalf (Codex, Cursor; extensible).
_Avoid_: tool, agent, vendor, provider; do not conflate with coding agent (the role)

**Harness Credentials**:
A generic credential blob — API key or a captured subscription auth file — identical in shape
either way. Captured once from a **host login** (a `vibing` command reads the harness's on-disk auth
file) and stored plaintext in the Control Plane (single-user local tool; see
[ADR-0012](docs/adr/0012-harness-credentials-are-host-captured-stored-plaintext-and-injected-per-container.md)).
**Written into the container by the Control Plane** via `devcontainer exec` (install-if-missing,
then the blob piped to the harness's credential path), not delivered over the runtime channel
(ADR-0019).
_Avoid_: secret, token (when ambiguous), api key (it is the api-key *or* file case)

**Harness Status**:
A managed harness's `installed`/`authenticated` state for its Devcontainer. **Computed by the
Control Plane** via `devcontainer exec` and cached, recomputed only on Control-Plane-observable
triggers (container start, post-install/auth, manual refresh). Keyed to **container-running**, not
runtime-connected — visible even with the runtime down (ADR-0019). Shown per-Devcontainer in the
web. A plain status, *not* an event in a log.
_Avoid_: runtime event, harness event

**Delegated Run**:
One one-shot execution of a *managed* Coding Harness, spawned through the Devcontainer Runtime's MCP
server when the main harness delegates a task. Carries a harness, a model, and a prompt; produces a
result. Unattended and fully autonomous (runs in the harness's bypass mode — no human to answer
approvals). Not durable or resumable — when it ends, it is done. Spawned and observed in-container via MCP (`get_status`/`get_result`); additionally reported to the Control Plane as a read-only snapshot projection over the runtime channel (ADR-0016). Non-durable — the CP projection is best-effort and may be empty after a runtime restart.
_Avoid_: agent-session, subagent session, job, task (when ambiguous)

**Command** _(removed, ADR-0019)_:
Formerly a Control Plane → Devcontainer Runtime message (`authenticate_harness`/`install_harness`).
That direction no longer exists — harness setup is Control-Plane `devcontainer exec`, so the runtime
channel is outbound-only (Runtime → Control Plane). Do not reintroduce a Command direction without
an ADR superseding 0019.

**Control Plane API Mocking**:
A frontend development mode where the browser receives mock `/api/v1` Control Plane HTTP responses
and live invalidation events without requiring a running Control Plane. A UI inspection aid, not a
substitute source of truth.
_Avoid_: backendless mode, fake backend, mock server

## Lifecycle

Two lifecycles, both owned by the **Control Plane**: the Devcontainer's, and the Devcontainer
Runtime's (nested — the Runtime only runs inside a running Devcontainer, but is started and stopped
independently).

### Devcontainer lifecycle

- States: `created → starting → running → stopping → stopped`, plus `error`.
- Commands map to the Dev Container CLI: start → `devcontainer up`, stop → stop the container by
  its `devcontainer.local_folder` label. Restart is not a command; it is stop then start.
- Start and stop are long-running. The HTTP endpoint returns `202 Accepted` and the Control Plane
  runs the CLI in a background task, writing status (`starting → running`, or `error`) directly as it
  progresses. The browser sees changes via the SSE invalidation stream.
- Injecting and launching the Devcontainer Runtime is a **separate, explicit, user-driven action**
  (`POST /{id}/inject-runtime`), never an automatic post-`up` step — the devcontainer is the user's
  and the Control Plane does not launch the runtime speculatively. The Runtime has its own
  user-controlled lifecycle (start/stop/restart) independent of the container's.
- "**Stop the devcontainer**" stops the container without deleting its reusable environment.

### Runtime lifecycle

The Devcontainer Runtime's state as the Control Plane observes it. Four resolved states:

- `connected` — the runtime's WebSocket is registered. The **durable truth**: derived from the live
  registry, so it survives a Control Plane restart (the runtime re-connects on its own).
- `launching` — injection is in flight: set when inject starts, cleared by *whichever comes first*,
  WS-connect (→ `connected`) or a ~30s timeout (→ `disconnected`). A `LiveStateStore` **transient**,
  lost on Control Plane restart.
- `error` — a synchronous inject failure (bootstrap install or preflight unreachable). A sticky
  `LiveStateStore` transient set when `inject()` returns failure; distinguishes a failed launch
  attempt from the `disconnected` catch-all. Cleared by a retry inject (→ `launching`), stop, or
  WS-connect. The reason is in the runtime log, not the state. A launch **timeout** stays
  `disconnected`.
- `disconnected` — the catch-all for *not connected*: never injected, stopped, crashed, or
  failed-to-launch. The state label intentionally does **not** distinguish these; the runtime logs
  do (streamed live via `runtime-logs/stream`).

Control is explicit and user-driven: start (`inject-runtime`), stop (`stop-runtime` — `docker exec`
kill via a PID file the runtime writes), restart (stop then start). Diagnosability splits two ways:
**bootstrap + preflight** (`docker cp`, `uv tool install`, then
a `vibing runtime preflight` HTTP probe of the control-plane `/api/v1/health`) runs first and is
reported **synchronously** at inject time; the runtime is **spawned only if that half passes**, so
an unreachable control plane fails before any process starts. **Post-launch output** lives in the
in-container runtime log, **streamed live** (`tail -f`) over a chunked-HTTP `runtime-logs/stream`
endpoint while the Logs view is open. There is no in-container supervisor and no auto-restart —
failures (including a failed preflight) surface to the user rather than being silently retried.

## Notes

The Control Plane is the **single writer of derived state and mutates it directly** — there is no
`runtime_events` log and no projection/reducer layer. When the Dev Container CLI advances the
lifecycle, when the Control Plane (re)computes Harness Status via `devcontainer exec`, or when a
Devcontainer Runtime reports Delegated Runs, the Control Plane writes the read model and publishes
an SSE invalidation in the same step. The runtime channel is **outbound-only** and carries two
message kinds, both Runtime → Control Plane: `register` and `delegated_runs` (ADR-0019).
