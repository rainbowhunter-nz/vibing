# Vibing

A local operations center for managing AI coding agents across isolated devcontainers. This glossary is the canonical language for the domain — code, docs, and conversation should use these terms.

## Language

**Devcontainer**:
The central persistent entity: one isolated development container bound to exactly one local folder path. Owns its agent-sessions, approvals, inbox, and history. Exists even when not running (`created`/`stopped`); "running" means the container is up. Everything else hangs off it.
_Avoid_: Workspace, project, environment, repo

**Agent Session**:
The durable conversation between a user and a coding agent inside a Devcontainer — *not* a single run. Identified by one stable id that is also the agent's own session id and names its Session Transcript. Re-openable: after a run ends it rests in a resumable state and can be **continued in place**, appending more turns to the same conversation. At most one is active per Devcontainer. The agent is Claude Code today, but the entity is named for the role, not the vendor — domain terms, table (`agent_sessions`), and FKs all use `agent_session`. Spelled "agent-session" in prose. "Claude" may appear in user-facing UI copy only.
_Avoid_: Claude session, agent run, single-shot run

**Control Plane**:
The backend (FastAPI + SQLite). The single hub: it holds all metadata, sends Commands to runtimes and consumes the Runtime Events they emit (over TCP/IP, star topology — see [ADR-0003](docs/adr/0003-runtimes-connect-to-the-control-plane-over-tcp-ip-in-a-star-topology.md)), and is the only writer of derived state. The frontend is a separate client over `/api/v1` HTTP and is *not* part of the Control Plane.
_Avoid_: server, backend, orchestrator; do not include the frontend

**Control Plane API Mocking**:
A frontend development mode where the browser receives mock `/api/v1` Control Plane HTTP responses and live invalidation events without requiring a running Control Plane. It is a UI inspection aid, not a substitute source of truth for Runtime Events or projections.
_Avoid_: backendless mode, fake backend, mock server

**Runtime**:
A process that executes Commands and emits Runtime Events. Two kinds: the **Host Runtime Worker** (owns Devcontainer lifecycle — containers on the host) and the **Devcontainer Runtime Agent** (owns Agent Session lifecycle, running inside a Devcontainer).
_Avoid_: worker, daemon (when ambiguous)

**Command**:
A control-plane request directed at a Runtime expressing user/system intent (e.g. `start_devcontainer`, `start_agent_session`). Flows Control Plane → Runtime. Restart is not a Command; it is a convenience workflow composed from stop then start.
_Avoid_: action, request, message

**Runtime Event**:
A structured, low-volume, persisted fact emitted by a Runtime to the Control Plane. The append-only single source of truth for everything a Runtime reports. A distinct channel from Session Output — terminal output is never a Runtime Event.
_Avoid_: message, notification, log

**Session Output**:
The high-volume raw character stream from an Agent Session's terminal. Ephemeral — deliberately not persisted (a non-goal). Kept separate from Runtime Events precisely so that persisting it in a future revision is a purely additive change (attach a sink), not a redesign. Distinct from the Session Stream: the live *chat* view is served by the structured Session Stream, not by this raw-character channel.
_Avoid_: log, terminal log (when it implies persistence)

**Session Stream**:
The live, incremental projection of an *active* Agent Session's conversation — the same turns as the Session Transcript, but built progressively as the agent works and pushed to the browser in real time (down to token-level partial text). Ephemeral: it exists only for the duration of a run and is never persisted; when the run ends it yields to the durable Session Transcript as the source of truth. The basis for the live chat view. Distinct from Session Output (raw terminal characters) and from the Session Transcript (the durable, on-demand source of truth for *what was said*).
_Avoid_: streaming transcript, live output, Session Output

**Session Transcript**:
The durable, append-only conversation history of an Agent Session — the structured record of turns the agent itself persists to disk, owned by the Devcontainer Runtime Agent. The single source of truth for *what was said*, and the basis for continuing the conversation. Fetched on demand from the runtime, never a projection of Runtime Events and not stored by the Control Plane. Distinct from Session Output (an ephemeral live character stream) and from a Session Summary (a one-line final record).
_Avoid_: conversation log, history, output

**Inbox Event**:
A stateful (`unread`/`read`/`resolved`) notification a human acts on, derived as a projection of the four notable Runtime Event types (question, approval request, failure, completion). Never a source of truth.
_Avoid_: notification, alert, message

**Approval Request**:
A pending action an Agent Session needs the user to approve or reject before proceeding. Status: `pending → approved | rejected`. No expiry state — if the session ends, an outstanding request is left `pending` and hidden.
_Avoid_: permission, confirmation, prompt; "denied" (use `rejected`)

**User Intervention**:
A human response required for an Agent Session to continue, such as answering a question or approving/rejecting an Approval Request. The intervention is the user action; an Inbox Event is only the projected notification for it.
_Avoid_: notification, inbox item, alert

**Session Summary**:
The final record of a terminated Agent Session (one per session), written on its terminal event. Outlives nothing — it is a projection, not a separate source of truth.
_Avoid_: report, recap

## Lifecycles

Two independent lifecycles. Keep the verbs distinct.

**Devcontainer lifecycle** — owned by the Host Runtime Worker.
- States: `created → starting → running → stopping → stopped`, plus `error`.
- Commands: `start_devcontainer`, `stop_devcontainer`.
- "**Stop the devcontainer**" stops the container without deleting its reusable environment; it necessarily ends any active agent-session inside it.

**Agent Session lifecycle** — owned by the Devcontainer Runtime Agent.
- States: `starting → running ⇄ waiting_for_approval → completed / failed / stopped`.
- The three end states are **resumable resting states, not terminal**: `resume_agent_session` takes any of them back to `starting`, continuing the same conversation.
- Commands: `start_agent_session`, `resume_agent_session`, `stop_agent_session`.
- "**Stop the agent-session**" ends the current run only; the devcontainer keeps running and the session can be resumed later.
- "**Resume the agent-session**" re-opens a rested session in place — same id, same conversation. Gated by the one-active-per-devcontainer invariant.

**Rules**: An agent-session can only be `starting`/`running` while its Devcontainer is `running`. Never say "stop the session" to mean the container, or "stop the devcontainer" to mean the agent run.

## Notes

*All* read-model state is a projection of the `runtime_events` stream, with no exceptions — Inbox, agent-session status, devcontainer status, approval-request status, and session summaries. See [ADR-0002](docs/adr/0002-inbox-is-a-projection-of-the-runtime-event-stream.md). Every state transition must have a corresponding Runtime Event or the projection goes stale. Commands never write projected state directly: a `resolve_approval` command produces an `approval_resolved` event, and only that event mutates the approval projection.
