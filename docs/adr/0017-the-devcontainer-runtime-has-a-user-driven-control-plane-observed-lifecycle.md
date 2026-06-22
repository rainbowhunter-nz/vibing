# The Devcontainer Runtime has a user-driven, Control-Plane-observed lifecycle; injection stays detached

Until now the Devcontainer Runtime was launched inject-and-forget: a `devcontainer exec` ran
`uv tool install … && nohup vibing runtime … &` and the Control Plane returned immediately, learning
the runtime existed only if it connected back over the WebSocket. When it *didn't* connect there was
no exit code, no logs, no signal beyond "not connected" — "the runtime didn't come up and we have no
idea why." We give the Runtime a **first-class lifecycle the Control Plane observes and the user
controls**, separate from the container's, without turning the Control Plane into a process
supervisor.

**The Control Plane does not hold the process open.** The tempting fix — keep the `exec` attached as
a child so the CP owns stdout/exit/kill directly — was **rejected**: it binds the runtime's lifetime
to the *Control Plane process* (a CP restart would kill every runtime in every container, each
needing re-injection), and the richer knowledge it buys is fragile exactly when wanted — after a CP
restart the held handle is gone anyway. The **WebSocket is already the restart-surviving liveness
signal**, so we keep the **detached launch** and make the WS the durable source of truth. We also
**rejected an in-container process manager (supervisord)**: it would break the deliberately minimal
container contract (ADR-0004/0011: package manager + egress, runtime `docker cp`'d not baked), add a
second "is it alive?" answer that can disagree with the WS, and — worst — its auto-restart would
*hide* the failures we are trying to surface.

**Observed state is three resolved values:** `connected` (WS registered — durable, survives CP
restart), `launching` (a `LiveStateStore` transient set on inject, cleared by whichever comes first,
WS-connect or a ~30s timeout), and `disconnected` (the catch-all for *not connected*: never injected,
stopped, crashed, or failed-to-launch). A richer model with distinct `failed`/`stopped`/`never-injected`
was **rejected** — in every disconnected case the user's action is identical (look at logs, then
start), so the distinction earns nothing; the logs disambiguate. The frontend `runtime_connected`
boolean is replaced by a `runtime.state` enum, resolved like devcontainer `status` (durable truth +
transient).

**Injection stays explicit, never automatic.** ADR-0014's "after a successful `up` the Control Plane
injects the runtime" is reversed: the devcontainer is the user's, and the Control Plane does not
launch the runtime speculatively. Start is `inject-runtime` (exists); stop is a new `stop-runtime`
that **`docker exec` kills via a PID file** the runtime writes (chosen over a graceful WS-shutdown
Command because that can't kill a runtime that is alive-but-wedged-and-disconnected — the case that
matters — and the runtime holds no durable state worth draining); restart is stop-then-start with no
dedicated endpoint.

**Diagnosability splits two ways, and fixes a latent bug.** The current payload backgrounds the
*entire* chain with a trailing `&` (looser precedence than `&&`), so the exec returns `0` before
`uv tool install` even runs — its exit code is meaningless and its output is lost — and because only
`nohup vibing runtime` is redirected to the log file, an install failure (the most likely cause)
short-circuits `&&`, never reaches `nohup`, and leaves **no log at all**. We **run install
synchronously** (detaching only the long-running runtime) so **bootstrap failures** (`docker cp`,
`uv tool install`) come back through the existing `RunResult` *at inject time* — the CP can set
`disconnected` with a reason immediately, no fetch — and we **unify all bootstrap + runtime output
into one in-container log** fetched **on demand** via a new `runtime-logs` endpoint (no speculative
`docker exec` on timeout). There is no auto-restart: failures surface to the user.

Re-scopes ADR-0014 (explicit injection, runtime lifecycle) and extends ADR-0004/0011 (runtime model).

**Amendment (2026-06-23): inject is two-phase, preflight gates spawn.** `inject()` now runs
in two halves: **bootstrap+preflight** (`docker cp` uv + wheel, `uv tool install`, then a
`vibing runtime preflight` HTTP `GET` of the control-plane `/api/v1/health` derived from the
*same resolved WS URL* the runtime will use) and **spawn** (the detached `nohup` launch),
issued as two separate `devcontainer exec` calls. The runtime is spawned **only if
bootstrap+preflight succeeds**, so an unreachable control plane (a wrong resolved IP — the
most common silent failure) fails before any process is launched. Surfacing stays log-only
and the resolved state stays coarse `disconnected`: the `PREFLIGHT FAILED:` line lands in the
unified log, streamed by [0018].

Status: accepted
