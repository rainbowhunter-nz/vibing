# Read-model state is a projection of the runtime-event stream

`runtime_events` is the single append-only source of truth for everything a Runtime reports. All derived read-model state is a projection over that stream, written only by the Control Plane:

- **Inbox** — for the four notable event types (`claude_asked_question`, `approval_requested`, `session_completed`, `session_failed`) the reducer writes one `inbox_event` carrying `unread`/`read`/`resolved` state. The two vocabularies map 1:1 through a single documented function.
- **Agent Session status** — the same reducer advances `agent_sessions.status` (`starting` → `running` ⇄ `waiting_for_approval` → `completed`/`failed`/`stopped`).
- **Devcontainer status**, **approval-request status**, and **session summaries** are likewise projections, written only by the reducer in response to events. In-progress states such as `starting` and `stopping` are also projected from Runtime Events (`devcontainer_starting`, `devcontainer_stopping`), not written directly when a Command is sent.

The rule is universal: *all* read-model state projects from the stream, with no exceptions, and Commands never write projected state directly (e.g. a `resolve_approval` command produces an `approval_resolved` event, and only that event mutates the approval projection).

We chose projection over independently-written state so there is one source of truth, no second place for status to drift, and marking an item read/resolved never mutates the event log. Projected vocabularies (`inbox_events.event_type`, `agent_sessions.status`, etc.) should be typed `Literal`s, not hand-maintained strings.

Status: accepted
