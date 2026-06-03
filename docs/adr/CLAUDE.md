# ADR Index

Architectural decisions for Vibing. One file per decision, `NNNN-slug.md`.

- [0001](0001-devcontainer-source-is-a-single-local-path.md) — A Devcontainer's source is a single `local_path` column, not a generic `source_type`/`source_value` descriptor.
- [0002](0002-inbox-is-a-projection-of-the-runtime-event-stream.md) — `runtime_events` is the single source of truth; all read-model state (inbox, statuses, approvals, summaries) is a projection of it.
- [0003](0003-runtimes-connect-to-the-control-plane-over-tcp-ip-in-a-star-topology.md) — Runtimes connect to the Control Plane over TCP/IP in a star topology; no runtime-to-runtime communication.
- [0004](0004-devcontainer-runtime-agents-connect-on-a-dedicated-endpoint-routed-by-devcontainer-id.md) — Devcontainer Runtime Agents connect on a dedicated `/runtime/agent/ws` endpoint, routed by `devcontainer_id`; host-worker-launched; shared transport in `src/vibing_runtime_client`.
- [0005](0005-frontend-live-updates-use-sse-invalidation-events.md) — Frontend live updates use one app-level SSE stream carrying lightweight invalidation events only; HTTP stays canonical, runtime WebSockets stay reserved for runtime traffic.
- [0006](0006-frontend-live-updates-use-stale-while-revalidate-in-a-custom-hook.md) — The SSE flash is fixed by making `useApiQuery` stale-while-revalidate, not by adopting TanStack Query or a shared cache layer.

**Keep this index up to date: add a one-line entry here whenever you add a new ADR.**
