# The Control Plane owns harness setup via `devcontainer exec`; the runtime is delegation-only

Coding Harness install/authenticate/status lived in the Devcontainer Runtime, driven over the
runtime WebSocket by `install_harness`/`authenticate_harness` Commands. We **move all harness
setup to the Control Plane**, executed directly in the container via `devcontainer exec`, and
shrink the runtime to the MCP delegation server plus `delegated_runs` reporting.

## Why

Install always executes *inside* the container regardless of who triggers it — so the only real
choice is the execution path. The Control Plane already drives every other container mutation
(`up`, stop, inject, stop-runtime, runtime-logs) by shelling in; harness setup is the same shape
of work and belongs there. Two payoffs:

- **Fewer moving parts.** The *entire* CP→Runtime Command vocabulary is exactly
  `{install_harness, authenticate_harness}`. Moving both to CP-driven exec **deletes the whole
  Command direction** — `Command`/`CommandType`/`CommandEnvelope`, the runtime's
  `command_handler` + command queue/consumer, and the `harness_status` push. The runtime channel
  collapses to **outbound-only** (register + `delegated_runs`). A class of "is the runtime
  connected to receive this Command?" failure modes disappears.
- **Observability.** Install/auth stream live over the Control Plane's existing chunked-HTTP
  pattern (ADR-0018), so the user watches an install run instead of it being buried in a runtime
  subprocess.

Moving *only* install was rejected: it leaves `authenticate_harness` (so the Command channel
survives) and creates a two-writer problem for harness status — the Control Plane writing
post-install while the runtime still pushes `harness_status` violates the single-writer invariant
of [ADR-0014](0014-the-control-plane-drives-devcontainers-directly-and-the-event-log-is-removed.md).
It adds parts without removing any. The split is only coherent if install **and** auth move
together.

## Shape

**`vibing_harness` package** — per-harness behavior over an injected `Executor` protocol
(`run` / `read` / `write`). It is the single home for all per-harness knowledge: binary name,
install/version/auth-check commands, home-relative credential path + serialization, spawn
argv/env, result extraction. Container-agnostic and dependency-light; each consumer supplies its
own `Executor`. This keeps "one source of per-harness truth" actually true across two processes —
the alternative (pure data, consumers orchestrate) re-implements the non-uniform bits (codex auth
is a *command*; cursor auth is a *file read*) in both the CP and the runtime.

**Control Plane** supplies a `DevcontainerExecutor(devcontainer_id)`:
- `run` → `devcontainer exec` (remoteUser-correct — **never** raw `docker exec`, which is root and
  installs to the wrong prefix).
- `write` → `devcontainer exec bash -c 'umask 077; mkdir -p …; cat > "$HOME/…"'` with the blob on
  **stdin** (no plaintext temp file on the host).
- `read` → `devcontainer exec bash -c 'cat …'`.

It owns:
- **install / authenticate** as **synchronous streaming POST** endpoints (chunked HTTP). On
  completion → recompute status → SSE invalidation. Install is idempotent, so a client disconnect
  mid-stream is benign (re-click).
- **harness status** computed via the executor and **cached in `LiveStateStore`**, recomputed only
  on Control-Plane-observable triggers: container start, post-install/auth, and a user-driven
  manual refresh. Status is keyed to **container-running**, not runtime-connected — visible even
  with the runtime down.

**Devcontainer Runtime** keeps a `LocalExecutor` purely so MCP `list_harnesses` and spawn
(`build_spawn_argv`/`spawn_env`) read the same `vibing_harness` descriptors. It no longer installs,
authenticates, writes credentials, or pushes `harness_status`.

`DevcontainerExecutor` needs a **PIPE-based runner** distinct from `DevcontainerCliAdapter`'s
temp-file `_default_runner` (which uses `stdin=DEVNULL` to dodge the `devcontainer up` keep-alive
pipe-hang). The hang caveat is specific to `up`; short-lived `devcontainer exec` calls stream over
pipes safely and need stdin for credential writes.

## Removed

- `vibing_protocol`: `CommandType`, `Command`, `CommandEnvelope`, `HarnessStatusEnvelope`/`Item`
  (keep `RegisterEnvelope`, `DelegatedRunsEnvelope`).
- runtime: `command_handler.py`; the command queue/consumer + command dispatch in
  `runtime_client.py`; `harness_manager` install/auth + the on-connect `harness_status` push.
- Control Plane: `install_harness`/`authenticate_harness` Command sending;
  `runtime_intake.record_harness_status`; harness-cache eviction-on-disconnect; `harness_status`
  handling in `runtime.py`.

The WebSocket still earns its keep — runtime liveness / `connected` state
([ADR-0017](0017-the-devcontainer-runtime-has-a-user-driven-control-plane-observed-lifecycle.md))
and `delegated_runs` observation
([ADR-0016](0016-control-plane-observes-delegated-runs-via-runtime-snapshots-and-adds-install-harness.md)).
Only the Command *direction* is removed.

Re-scopes [0011](0011-devcontainer-runtime-agent-manages-harnesses-and-hosts-an-mcp-server.md)
(the runtime no longer manages harnesses — delegation only). Amends
[0012](0012-harness-credentials-are-host-captured-stored-plaintext-and-injected-per-container.md)
(credentials are written by a Control Plane `devcontainer exec`, not delivered via an
`authenticate_harness` Command). Re-scopes
[0016](0016-control-plane-observes-delegated-runs-via-runtime-snapshots-and-adds-install-harness.md)
(the `install_harness` Command it added is removed).

Status: accepted
