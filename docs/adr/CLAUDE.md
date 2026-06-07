# ADR Index

Architectural decisions for Vibing. One file per decision, `NNNN-slug.md`.

- [0001](0001-devcontainer-source-is-a-single-local-path.md) — A Devcontainer's source is a single `local_path` column, not a generic `source_type`/`source_value` descriptor.
- [0002](0002-inbox-is-a-projection-of-the-runtime-event-stream.md) — `runtime_events` is the single source of truth; all read-model state (inbox, statuses, approvals, summaries) is a projection of it.
- [0003](0003-runtimes-connect-to-the-control-plane-over-tcp-ip-in-a-star-topology.md) — Runtimes connect to the Control Plane over TCP/IP in a star topology; no runtime-to-runtime communication.
- [0004](0004-devcontainer-runtime-agents-connect-on-a-dedicated-endpoint-routed-by-devcontainer-id.md) — Devcontainer Runtime Agents connect on a dedicated `/runtime/agent/ws` endpoint, routed by `devcontainer_id`; host-worker-launched; shared transport in `src/vibing_runtime_client`. (Amended 2026-06-05: the runtime is injected via `docker cp` of `uv` + wheel at launch, not baked into the image.)
- [0005](0005-frontend-live-updates-use-sse-invalidation-events.md) — Frontend live updates use one app-level SSE stream carrying lightweight invalidation events only; HTTP stays canonical, runtime WebSockets stay reserved for runtime traffic.
- [0006](0006-frontend-live-updates-use-stale-while-revalidate-in-a-custom-hook.md) — The SSE flash is fixed by making `useApiQuery` stale-while-revalidate, not by adopting TanStack Query or a shared cache layer.
- [0007](0007-control-plane-api-mocking-uses-msw-and-a-dev-eventsource-adapter.md) — Frontend Control Plane API Mocking uses MSW for `/api/v1` HTTP and a dev-only EventSource adapter for manual live invalidation testing.
- [0008](0008-agent-sessions-are-durable-resumable-conversations-keyed-by-the-agents-session-id.md) — An Agent Session is the durable conversation (not one run), keyed by the agent's own session id (`--session-id`); end states are resumable via `resume_agent_session`; Session Summary becomes upsert-by-session.
- [0009](0009-session-transcripts-are-fetched-via-request-reply-over-the-runtime-channel-and-never-persisted.md) — Session Transcripts are fetched on demand via a new request/reply pattern (correlation id) over the agent WebSocket, parsed to normalized turns by the agent, never persisted; degrade to Session Summary when stopped.
- [0010](0010-agent-sessions-stream-live-structured-turns-over-a-per-session-sse-channel.md) — Agent Sessions stream live structured turn-deltas over a per-session SSE channel (separate from the invalidation `/events` stream); the transcript stays the source of truth, turns gain a stable `id` (Claude uuid) for live/durable reconciliation.

**Keep this index up to date: add a one-line entry here whenever you add a new ADR.**
