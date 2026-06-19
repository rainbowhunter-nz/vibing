# ADR Index

Architectural decisions for Vibing. One file per decision, `NNNN-slug.md`.

- [0001](0001-devcontainer-source-is-a-single-local-path.md) — A Devcontainer's source is a single `local_path` column, not a generic `source_type`/`source_value` descriptor.
- [0002](0002-inbox-is-a-projection-of-the-runtime-event-stream.md) — **SUPERSEDED by [0014].** `runtime_events` is the single source of truth; all read-model state is a projection of it.
- [0003](0003-runtimes-connect-to-the-control-plane-over-tcp-ip-in-a-star-topology.md) — **SUPERSEDED by [0014].** Runtimes connect to the Control Plane over TCP/IP in a star topology.
- [0004](0004-devcontainer-runtime-agents-connect-on-a-dedicated-endpoint-routed-by-devcontainer-id.md) — Devcontainer Runtime Agents connect on a dedicated `/runtime/agent/ws` endpoint, routed by `devcontainer_id`; host-worker-launched; shared transport in `src/vibing_runtime_client`. (Amended 2026-06-05: the runtime is injected via `docker cp` of `uv` + wheel at launch, not baked into the image.)
- [0005](0005-frontend-live-updates-use-sse-invalidation-events.md) — Frontend live updates use one app-level SSE stream carrying lightweight invalidation events only; HTTP stays canonical, runtime WebSockets stay reserved for runtime traffic.
- [0006](0006-frontend-live-updates-use-stale-while-revalidate-in-a-custom-hook.md) — The SSE flash is fixed by making `useApiQuery` stale-while-revalidate, not by adopting TanStack Query or a shared cache layer.
- [0007](0007-control-plane-api-mocking-uses-msw-and-a-dev-eventsource-adapter.md) — Frontend Control Plane API Mocking uses MSW for `/api/v1` HTTP and a dev-only EventSource adapter for manual live invalidation testing.
- [0008](0008-agent-sessions-are-durable-resumable-conversations-keyed-by-the-agents-session-id.md) — **SUPERSEDED by [0015].** An Agent Session is the durable conversation, keyed by the agent's own session id; end states resumable.
- [0009](0009-session-transcripts-are-fetched-via-request-reply-over-the-runtime-channel-and-never-persisted.md) — **SUPERSEDED by [0015].** Session Transcripts fetched on demand via request/reply over the agent WebSocket.
- [0010](0010-agent-sessions-stream-live-structured-turns-over-a-per-session-sse-channel.md) — **SUPERSEDED by [0015].** Agent Sessions stream live structured turn-deltas over a per-session SSE channel.
- [0011](0011-devcontainer-runtime-agent-manages-harnesses-and-hosts-an-mcp-server.md) — **Re-scoped by [0015]** (Agent Session half dropped). The Devcontainer Runtime manages Coding Harnesses (check/install/authenticate) and hosts a runtime-owned streamable-HTTP MCP server so the main harness can spawn Delegated Runs.
- [0012](0012-harness-credentials-are-host-captured-stored-plaintext-and-injected-per-container.md) — Harness credentials are captured from a one-time host login, stored plaintext in the Control Plane, delivered on demand via an `authenticate_harness` Command, and adapter-injected (install-on-demand) per container; one generic blob shape for api-key or subscription auth.
- [0013](0013-delegated-runs-are-unattended-autonomous-concurrent-runs-not-agent-sessions.md) — **Re-scoped by [0015]** (in-container only, not reported up). Delegated Runs (MCP `spawn`) are unattended, fully-autonomous, concurrent (capped) in-container runs that share the workspace tree, but are NOT Agent Sessions.
- [0014](0014-the-control-plane-drives-devcontainers-directly-and-the-event-log-is-removed.md) — The Control Plane drives the Devcontainer lifecycle directly in-process (no Host Runtime Worker, no multi-machine); the `runtime_events` log and projection/reducer layer are removed in favor of direct read-model writes. Supersedes 0002, 0003.
- [0015](0015-drop-the-agent-session-model-the-devcontainer-runtime-is-a-harness-friction-companion.md) — Drop the Agent Session model entirely; the Devcontainer Runtime is re-framed as the in-container companion that reduces Coding Harness friction (harness management + MCP delegation today, extensible). Supersedes 0008–0010; re-scopes 0011, 0013.

**Keep this index up to date: add a one-line entry here whenever you add a new ADR.**
