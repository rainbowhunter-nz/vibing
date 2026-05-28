# Vibing Runtime Boundaries

This document fixes the responsibilities of the Vibing MVP runtimes and the
shape of the messages that flow between them. It complements
`docs/domain-model.md` (which defines the product vocabulary) by tying that
vocabulary to runtime code.

The MVP has two runtimes:

- The **Host Runtime Worker**, owned by the backend (`apps/api`).
- The **Workspace Runtime Agent**, owned by `packages/workspace_runtime`.

The two communicate through a control plane carrying typed `Command` and
`RuntimeEvent` messages defined in `packages/protocol` (`vibing_protocol`).

## Host runtime responsibilities

The Host Runtime Worker is responsible for everything that lives outside the
workspace container, on the developer's machine.

- Preparing the workspace environment (eventually: invoking the Dev Container
  CLI, Docker, or Podman).
- Starting, stopping, and restarting the workspace runtime environment.
- Reporting workspace-level lifecycle outcomes through `RuntimeEvent`s:
  `workspace_started`, `workspace_failed`.
- Owning the host-side end of the control plane.

The host runtime does **not** know anything about Claude Code, PTY, or session
state. Those live in the workspace runtime.

## Workspace runtime responsibilities

The Workspace Runtime Agent is responsible for everything that happens inside
the workspace container, around one Claude Code session at a time.

- Starting the Claude Code session inside the workspace.
- Managing the PTY and session I/O.
- Routing user input back to Claude Code.
- Detecting questions and approval requests, and reporting them as
  `RuntimeEvent`s.
- Reporting session lifecycle and outcomes:
  `claude_session_started`, `claude_asked_question`, `approval_requested`,
  `approval_resolved`, `session_completed`, `session_failed`.
- Future: surfacing workspace Git state changes.

The workspace runtime does **not** know about container engines, the host
filesystem outside the workspace, or other workspaces.

## Control-plane message shapes

The control plane carries two message kinds, both defined in
`packages/protocol/src/vibing_protocol/`.

### `Command`

A request directed *at* a runtime. Fields:

- `type: CommandType` — one of the literal command names below.
- `workspace_id: str | None`
- `agent_session_id: str | None`
- `payload: dict[str, Any] | None`

`CommandType` literal:

```
start_workspace
stop_workspace
restart_workspace
start_claude_session
stop_claude_session
send_user_input
resolve_approval
```

### `RuntimeEvent`

A structured event emitted *from* a runtime. Fields:

- `id: str` (UUID4)
- `workspace_id: str | None`
- `agent_session_id: str | None`
- `event_type: EventType` — one of the literal event names below.
- `source: RuntimeEventSource` — `host_runtime_worker` or
  `workspace_runtime_agent`.
- `payload: dict[str, Any] | None`
- `created_at: str` (ISO 8601 with UTC offset)

`EventType` literal:

```
workspace_started
workspace_failed
claude_session_started
claude_asked_question
approval_requested
approval_resolved
session_completed
session_failed
```

This document does not define a transport. Today the only consumer is the
backend's `runtime_events` table; future tickets add a dispatcher and/or
wire protocol between the host and workspace processes.

## Command routing

Each command type belongs to exactly one runtime.

| Command | Routed to |
| --- | --- |
| `start_workspace` | Host runtime |
| `stop_workspace` | Host runtime |
| `restart_workspace` | Host runtime |
| `start_claude_session` | Workspace runtime |
| `stop_claude_session` | Workspace runtime |
| `send_user_input` | Workspace runtime |
| `resolve_approval` | Workspace runtime |

The routing is exposed in code as `HOST_COMMAND_TYPES`
(`vibing_api.host_runtime`) and `WORKSPACE_COMMAND_TYPES`
(`vibing_workspace_runtime`). No dispatcher consumes those constants yet; a
future ticket adds one.

## Event-name alignment with the Product Foundation event model

`docs/domain-model.md` lists *example* runtime event names. The
type-checked, canonical set is `vibing_protocol.EventType` and is what the
implementation uses today; several canonical names differ from the examples
in the domain model (e.g. `claude_session_started` rather than
`session_started`, `claude_asked_question` rather than `question_detected`).
The mapping back to domain concepts:

| `EventType` | Source | Domain-model concept |
| --- | --- | --- |
| `workspace_started` | host_runtime_worker | workspace `running` |
| `workspace_failed` | host_runtime_worker | workspace `error`; produces `workspace_error` inbox event |
| `claude_session_started` | workspace_runtime_agent | agent session `running` |
| `claude_asked_question` | workspace_runtime_agent | produces `question` inbox event; session `waiting_for_user_input` |
| `approval_requested` | workspace_runtime_agent | new `approval_request`; produces `approval_request` inbox event |
| `approval_resolved` | workspace_runtime_agent | approval request `approved` or `rejected` |
| `session_completed` | workspace_runtime_agent | session `completed`; produces `completion` inbox event |
| `session_failed` | workspace_runtime_agent | session `failed`; produces `failure` inbox event |

`docs/domain-model.md` is not updated by this document. Future tickets that
expand the runtime surface (e.g. `git_status_changed`) extend `EventType`
and update this table at the same time.

## Intentionally out of scope for Product Foundation

The runtime skeletons present today do not implement:

- Docker, Podman, or any container engine call.
- Dev Container CLI invocation.
- Claude Code process launch or management.
- PTY handling, streaming output, terminal scrollback.
- Inbox-event side effects, approval-queue side effects.
- Git visibility or the changed-files view.
- Editor integration (VS Code, native, browser).
- Any long-running background worker.
- A control-plane transport (HTTP, queue, IPC) between the two runtimes.
- A `commands` SQLite table; commands are not persisted in the MVP.

Each of these lands in its own future ticket, against the contracts defined
above.
