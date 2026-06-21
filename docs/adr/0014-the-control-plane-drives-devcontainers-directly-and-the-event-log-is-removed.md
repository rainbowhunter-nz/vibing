# The Control Plane drives Devcontainers directly; the Host Runtime Worker and event log are removed

The project was scoped for multi-machine from the start: a separate **Host Runtime Worker** process
connected to the Control Plane over a WebSocket (ADR-0003, star topology) and drove the Dev Container
CLI on the host, emitting devcontainer-lifecycle **Runtime Events** that the Control Plane persisted
to an append-only `runtime_events` log and projected into read models (ADR-0002). In practice this is
a single-user, single-machine tool. The worker, its WebSocket channel, the event log, and the
projection/reducer layer are all cost with no payoff at this scale.

We **remove multi-machine support and fold the host worker into the Control Plane.** The Control
Plane now shells out to the Dev Container CLI **in-process**: start → `devcontainer up`, stop → stop
the container by its `devcontainer.local_folder` label. Because `up`/`stop` are slow, the HTTP
endpoint returns `202 Accepted` and the work runs in a background task. After a successful `up`, the
Control Plane injects and launches the Devcontainer Runtime into the container — the same injection
the worker used to do, now a local call.

We also **remove the event-sourcing layer.** There is no `runtime_events` table, no reducer, no
`project()`. The Control Plane is still the single writer of derived state, but it **mutates the read
model directly** and publishes an SSE invalidation in the same step — when the CLI advances the
lifecycle, or when a Devcontainer Runtime reports Harness Status. This reverses ADR-0002's "every
read model is a projection of the event log." We accept losing event replay/audit history: it was
earning its keep through multi-consumer projections and an audit trail that a local single-user tool
does not need, and the only remaining consumers (devcontainer status, harness status) are trivial
direct writes.

The Devcontainer Runtime still connects **over a WebSocket** (ADR-0004) — it lives in a separate
container network namespace, so it genuinely needs the network hop and a reconnect loop. Only the
*host* side stopped being remote.

Consequences: the host worker package (`vibing_host_runtime`) and the `vibing host-runtime` CLI are
deleted; the shared `vibing_runtime_client` is folded into the Devcontainer Runtime (its only
remaining consumer). The Control Plane gains in-process subprocess execution and background tasks,
so a crash mid-`up` can leave a container half-started with no event trail to replay — acceptable for
a tool the user runs and watches locally.

Supersedes: ADR-0002, ADR-0003.

Status: accepted

---

**Note (2026-06-22 — live-state refactor):** The phrase "the only remaining consumers (devcontainer status, harness status) are trivial direct writes" is no longer accurate. Both are now **live/in-memory**, not DB writes: devcontainer `status` is computed on each request (transient `LiveStateStore` map → Docker label), and harness status is cached in `LiveStateStore` and evicted on runtime disconnect. The `harness_status` table and `devcontainers.status` column have been removed (schema v8). `delegated_runs` remains a DB-backed projection per ADR-0016.
