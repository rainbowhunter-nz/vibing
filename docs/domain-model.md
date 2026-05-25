# Vibing MVP Domain Model

This document defines the canonical MVP vocabulary for Vibing.

The purpose of this document is to keep the frontend, backend, host runtime, workspace runtime, and product documentation using the same language.

VIB-3 is intentionally a shared vocabulary and product/domain definition task. It should not introduce a heavy database schema, event bus implementation, or premature abstraction layer.

## Canonical naming rules

Use human-friendly labels in the UI, but use stable snake_case names in code, API contracts, and persisted values.

Important distinction:

- `completed` is a session status.
- `completion` is an inbox event type.

This keeps status words and event words separate.

## Core concepts

## Workspace

A workspace is one isolated development environment for one local project.

A workspace contains the project source code, workspace configuration, runtime state, editor access, Git state when the local project is a Git repository, and at most one active Claude Code session for the MVP.

MVP source rule:

- A workspace is created from an existing local folder only.
- The canonical source field is `local_path`.
- Git URL workspace creation and repository cloning are not part of the MVP.

The Host Runtime Worker owns workspace lifecycle operations such as creating, starting, stopping, restarting, and deleting the workspace environment.

Suggested MVP fields:

- `id`
- `name`
- `local_path`
- `status`
- `container_id`
- `created_at`
- `updated_at`

### Workspace statuses

| Status | Meaning |
| --- | --- |
| `created` | The workspace metadata exists, but the runtime environment is not currently running. |
| `starting` | Vibing is preparing or starting the workspace runtime environment. |
| `running` | The workspace runtime environment is available. |
| `stopping` | Vibing is stopping the workspace runtime environment. |
| `stopped` | The workspace runtime environment has been stopped. |
| `error` | The workspace failed to start, became unhealthy, or encountered a runtime error. |
| `deleted` | The workspace has been removed from Vibing's active workspace list. |

Avoid using `active` as a workspace status because it can be confused with an active agent session.

## Agent Session

An agent session is one Claude Code session running inside a workspace.

For the MVP, each workspace may have at most one active Claude Code session at a time.

The Workspace Runtime Agent owns starting Claude Code, managing the PTY/session, streaming output, sending user input back to Claude Code, detecting questions and approval requests, reporting status, and producing the final session summary.

### Agent session statuses

| Status | Meaning |
| --- | --- |
| `running` | Claude Code is actively running, or Vibing has no evidence that it needs user attention. |
| `waiting_for_approval` | Claude Code is blocked until the user approves or rejects a requested action. |
| `waiting_for_user_input` | Claude Code is waiting for a user answer, clarification, or instruction. |
| `completed` | The session finished successfully or reached a normal stopping point. |
| `failed` | The session ended because of an error or unrecoverable failure. |

## Inbox Event

An inbox event is an important event that Vibing surfaces to the user across all workspaces.

The inbox exists so the user does not need to watch every terminal or session view to notice questions, approvals, failures, completions, or workspace errors.

An inbox event may reference a workspace, an agent session, an approval request, or a final session summary.

### Inbox event types

| Type | Meaning |
| --- | --- |
| `question` | Claude Code asked the user a question or requested clarification. |
| `approval_request` | Claude Code requested approval for an action. |
| `failure` | A session failed or hit an unrecoverable error. |
| `completion` | A session completed or reached a normal stopping point. |
| `workspace_error` | The workspace runtime encountered an infrastructure or health error. |

### Inbox event statuses

| Status | Meaning |
| --- | --- |
| `unread` | The user has not yet seen or acknowledged the event. |
| `read` | The user has seen the event, but it may not be fully resolved. |
| `resolved` | The event no longer needs user attention. |

## Approval Request

An approval request is a specific request from Claude Code that requires a user decision.

Approval requests are separate from inbox events because they have their own decision lifecycle. An approval request can create an inbox event, but the approval request remains the source of truth for whether the action is pending, approved, or rejected.

### Approval request statuses

| Status | Meaning |
| --- | --- |
| `pending` | The request is waiting for the user's decision. |
| `approved` | The user approved the requested action. |
| `rejected` | The user rejected the requested action. |

## Session Summary

A session summary is the final persisted summary of a stopped, completed, or failed agent session.

The MVP persists important operational history, but not full terminal scrollback. The session summary gives the user a durable record of what happened after the live session output is gone.

A session summary should capture:

- final status
- start/end timestamps
- last known event
- related inbox events
- related approval requests
- summary text

`final_status` should use terminal agent session statuses such as `completed` and `failed`. Do not add extra final statuses until the lifecycle explicitly requires them.

## Runtime Event

A runtime event is a structured event emitted by the Host Runtime Worker or Workspace Runtime Agent to the control plane.

Runtime events are how lower-level runtime activity becomes product-visible state, inbox events, approval requests, status changes, and session summaries.

For VIB-3, this is a vocabulary definition only. Do not implement a full event bus or event-sourcing system as part of this ticket.

### Example runtime event names

| Event | Source | Meaning |
| --- | --- | --- |
| `workspace_started` | Host Runtime Worker | A workspace runtime environment started successfully. |
| `workspace_failed` | Host Runtime Worker | A workspace runtime environment failed or became unhealthy. |
| `session_started` | Workspace Runtime Agent | A Claude Code session started. |
| `session_status_changed` | Workspace Runtime Agent | A session moved to a new structured status. |
| `approval_requested` | Workspace Runtime Agent | Claude Code requested user approval. |
| `question_detected` | Workspace Runtime Agent | Claude Code asked the user a question. |
| `session_completed` | Workspace Runtime Agent | A session completed normally. |
| `session_failed` | Workspace Runtime Agent | A session failed. |
| `git_status_changed` | Workspace Runtime Agent | The workspace Git state changed. |

## Relationship summary

- A workspace can have many historical agent sessions.
- A workspace can have at most one active agent session in the MVP.
- An agent session belongs to one workspace.
- An inbox event usually belongs to one workspace and may belong to one agent session.
- An approval request belongs to one workspace and one agent session.
- An approval request may create or be linked from an inbox event.
- A session summary belongs to one completed or failed agent session.
- Runtime events are internal structured signals that update product state.

## MVP non-goals for this domain model

Do not introduce the following as part of VIB-3:

- Git URL workspace creation or repository cloning.
- Codex or other non-Claude coding agents.
- Multiple concurrent sessions in one workspace.
- Multi-user ownership, RBAC, or audit vocabulary.
- A full event-sourcing model.
- Full terminal scrollback persistence.
- A custom editor domain model.
- A plugin SDK vocabulary.