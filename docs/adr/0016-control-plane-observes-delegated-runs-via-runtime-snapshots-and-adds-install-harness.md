# The Control Plane observes Delegated Runs via runtime-pushed snapshots; add install_harness

ADR-0015 scoped Delegated Runs as **in-container only** — observable solely by the main
harness through MCP, with the Control Plane explicitly not tracking them. To let the Control
Plane (and, later, the web UI) observe delegated activity, we **amend that stance**: the
Devcontainer Runtime now reports Delegated Runs up the existing runtime WebSocket, and the
Control Plane keeps a **read-only projection** of them.

**Reporting is a snapshot, not a delta stream.** On every run state change (spawn→running,
terminal, stop) and once on connect, the runtime sends the *full current run list* for its
devcontainer as a `delegated_runs` envelope. The Control Plane **replaces** its stored set for
that devcontainer. This mirrors `harness_status`: idempotent, ordering-tolerant, and
self-healing — a runtime that restarts (losing its in-memory runs) reconnects and replaces the
CP set with its current (likely empty) state, so the projection never drifts permanently. Deltas
were rejected: they need per-event delivery guarantees the single best-effort WebSocket does not
provide, and they complicate restart reconciliation.

The Control Plane stores the projection in a `delegated_runs` read-model table, written directly
(ADR-0014 style: no event log) when a snapshot arrives, and publishes a `delegated_runs` SSE
invalidation. Runs remain **non-durable and in-container-spawned**: the CP projection is
best-effort and may be empty or stale immediately after a runtime restart. We accept this — it is
observation, not a system of record.

We also add an **`install_harness` Command** (Control Plane → Runtime), separate from
`authenticate_harness` (which still installs-on-demand). It calls the per-harness adapter's
existing `install()` and reports `harness_status` back, giving an explicit install action without
delivering credentials.

This re-scopes ADR-0013 (Delegated Runs are now reported up, as a projection) and amends
ADR-0015's in-container-only stance. The web UI is **not** wired to the stored runs yet — the
frontend-facing `GET /delegated-runs` stays an empty stub; that exposure is deferred. The runtime
channel grows a fourth message kind (`delegated_runs`, Runtime → Control Plane) and the Command
vocabulary grows `install_harness`.

Status: accepted
