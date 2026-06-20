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
The in-container companion process, one per running Devcontainer. Its purpose is to reduce the
friction of using Coding Harnesses inside an ephemeral container and to add capability on top of
them. Today it (1) checks/installs/authenticates *managed* harnesses from credentials the Control
Plane delivers and reports their Harness Status, and (2) hosts an MCP server the main harness calls
to start Delegated Runs. Designed to grow more capabilities (e.g. skills management). Connects out
to the Control Plane over a WebSocket, routed by `devcontainer_id`.
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
Delivered **on demand** to a Devcontainer Runtime via an `authenticate_harness` Command; the
per-harness adapter installs the harness if missing and drops the credential into place.
_Avoid_: secret, token (when ambiguous), api key (it is the api-key *or* file case)

**Harness Status**:
The Devcontainer Runtime's report of a managed harness's `installed`/`authenticated` state for its
Devcontainer. Reported up over the runtime WebSocket on connect and after each authenticate, written
directly to the read model by the Control Plane, and shown per-Devcontainer in the web. A plain
status report, *not* an event in a log.
_Avoid_: runtime event, harness event

**Delegated Run**:
One one-shot execution of a *managed* Coding Harness, spawned through the Devcontainer Runtime's MCP
server when the main harness delegates a task. Carries a harness, a model, and a prompt; produces a
result. Unattended and fully autonomous (runs in the harness's bypass mode — no human to answer
approvals). Not durable or resumable — when it ends, it is done. Spawned and observed in-container via MCP (`get_status`/`get_result`); additionally reported to the Control Plane as a read-only snapshot projection over the runtime channel (ADR-0016). Non-durable — the CP projection is best-effort and may be empty after a runtime restart.
_Avoid_: agent-session, subagent session, job, task (when ambiguous)

**Command**:
A message the Control Plane sends to a Devcontainer Runtime expressing intent. The extensible
runtime channel; today `authenticate_harness` and `install_harness`. Flows Control Plane → Devcontainer Runtime.
_Avoid_: action, request, message; not used for the Devcontainer lifecycle (the Control Plane drives
that in-process, not via a Command)

**Control Plane API Mocking**:
A frontend development mode where the browser receives mock `/api/v1` Control Plane HTTP responses
and live invalidation events without requiring a running Control Plane. A UI inspection aid, not a
substitute source of truth.
_Avoid_: backendless mode, fake backend, mock server

## Lifecycle

One lifecycle now — the Devcontainer's, owned by the **Control Plane**.

- States: `created → starting → running → stopping → stopped`, plus `error`.
- Commands map to the Dev Container CLI: start → `devcontainer up`, stop → stop the container by
  its `devcontainer.local_folder` label. Restart is not a command; it is stop then start.
- Start and stop are long-running. The HTTP endpoint returns `202 Accepted` and the Control Plane
  runs the CLI in a background task, writing status (`starting → running`, or `error`) directly as it
  progresses. The browser sees changes via the SSE invalidation stream.
- After a successful `up`, the Control Plane injects and launches the Devcontainer Runtime into the
  container.
- "**Stop the devcontainer**" stops the container without deleting its reusable environment.

## Notes

The Control Plane is the **single writer of derived state and mutates it directly** — there is no
`runtime_events` log and no projection/reducer layer. When the Dev Container CLI advances the
lifecycle, or a Devcontainer Runtime reports Harness Status, the Control Plane writes the read model
and publishes an SSE invalidation in the same step. The runtime channel carries four message kinds: `register`, `command` (Control Plane → Runtime), `harness_status` and `delegated_runs` (Runtime → Control Plane).
