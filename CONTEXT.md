# Vibing

A local operations center for managing AI coding agents across isolated devcontainers. This glossary is the canonical language for the domain — code, docs, and conversation should use these terms.

## Language

**Devcontainer**:
The central persistent entity: one isolated development container bound to exactly one local folder path. Owns its agent-sessions, approvals, inbox, and history. Exists even when not running (`created`/`stopped`); "running" means the container is up. Everything else hangs off it.
_Avoid_: Workspace, project, environment, repo

**Agent Session**:
A single run of a coding agent inside a running Devcontainer. At most one is active per Devcontainer. The agent is Claude Code today, but the entity is named for the role, not the vendor — domain terms, table (`agent_sessions`), and FKs all use `agent_session`. Spelled "agent-session" in prose. "Claude" may appear in user-facing UI copy only.
_Avoid_: Claude session, agent run, conversation

**Control Plane**:
The backend (FastAPI + SQLite). The single hub: it holds all metadata, sends Commands to runtimes and consumes the Runtime Events they emit (over TCP/IP, star topology — see [ADR-0003](docs/adr/0003-runtimes-connect-to-the-control-plane-over-tcp-ip-in-a-star-topology.md)), and is the only writer of derived state. The frontend is a separate client over `/api/v1` HTTP and is *not* part of the Control Plane.
_Avoid_: server, backend, orchestrator; do not include the frontend

**Runtime**:
A process that executes Commands and emits Runtime Events. Two kinds: the **Host Runtime Worker** (owns Devcontainer lifecycle — containers on the host) and the **Devcontainer Runtime Agent** (owns Agent Session lifecycle, running inside a Devcontainer).
_Avoid_: worker, daemon (when ambiguous)

**Command**:
A control-plane request directed at a Runtime expressing user/system intent (e.g. `start_devcontainer`, `start_agent_session`). Flows Control Plane → Runtime.
_Avoid_: action, request, message

**Runtime Event**:
A structured, low-volume, persisted fact emitted by a Runtime to the Control Plane. The append-only single source of truth for everything a Runtime reports. A distinct channel from Session Output — terminal output is never a Runtime Event.
_Avoid_: message, notification, log

**Session Output**:
The high-volume character stream from an Agent Session's terminal, carried on its own channel for the live session view. Ephemeral in MVP — deliberately not persisted (a non-goal). Kept separate from Runtime Events precisely so that persisting it in a future revision is a purely additive change (attach a sink), not a redesign.
_Avoid_: log, transcript, terminal log (when it implies persistence)

**Inbox Event**:
A stateful (`unread`/`read`/`resolved`) notification a human acts on, derived as a projection of the four notable Runtime Event types (question, approval request, failure, completion). Never a source of truth.
_Avoid_: notification, alert, message

**Approval Request**:
A pending action an Agent Session needs the user to approve or reject before proceeding. Status: `pending → approved | rejected`. No expiry state — if the session ends, an outstanding request is left `pending` and hidden.
_Avoid_: permission, confirmation, prompt; "denied" (use `rejected`)

**Session Summary**:
The final record of a terminated Agent Session (one per session), written on its terminal event. Outlives nothing — it is a projection, not a separate source of truth.
_Avoid_: report, recap

## Lifecycles

Two independent lifecycles. Keep the verbs distinct.

**Devcontainer lifecycle** — owned by the Host Runtime Worker.
- States: `created → starting → running → stopping → stopped`, plus `error`.
- Commands: `start_devcontainer`, `stop_devcontainer`, `restart_devcontainer`.
- "**Stop the devcontainer**" stops the container, which necessarily ends any active agent-session inside it.

**Agent Session lifecycle** — owned by the Devcontainer Runtime Agent.
- States: `starting → running ⇄ waiting_for_approval → completed / failed / stopped`.
- Commands: `start_agent_session`, `stop_agent_session`.
- "**Stop the agent-session**" ends the agent run only; the devcontainer keeps running.

**Rules**: An agent-session can only be `starting`/`running` while its Devcontainer is `running`. Never say "stop the session" to mean the container, or "stop the devcontainer" to mean the agent run.

## Notes

*All* read-model state is a projection of the `runtime_events` stream, with no exceptions — Inbox, agent-session status, devcontainer status, approval-request status, and session summaries. See [ADR-0002](docs/adr/0002-inbox-is-a-projection-of-the-runtime-event-stream.md). Every state transition must have a corresponding Runtime Event or the projection goes stale. Commands never write projected state directly: a `resolve_approval` command produces an `approval_resolved` event, and only that event mutates the approval projection.
