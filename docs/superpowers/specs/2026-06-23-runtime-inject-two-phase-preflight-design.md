# Two-phase runtime inject: bootstrap + preflight, then spawn

## Problem

`RuntimeInjector.inject()` does bootstrap (`docker cp` uv + wheel, `uv tool install`)
and launch (`nohup vibing runtime devcontainer &`) in one `devcontainer exec`. The
runtime then connects back over WebSocket to a control-plane URL that
`resolve_runtime_control_plane_url` *guesses* (`host.docker.internal` → the container's
own IP). When that guess is wrong, the runtime is spawned, fails to connect, and the
only signal is `disconnected` ~30s later — we spawned a process that never had a chance.

We want inject to refuse to spawn when the control plane isn't reachable from inside the
container, and to make the reason visible.

## Decision

Split `inject()` into two halves, gated:

1. **Bootstrap + preflight** — copy uv + wheel, install vibing, then probe that the
   control plane is reachable from *inside* the container. If either step fails, surface
   the reason to the unified log and **do not spawn**.
2. **Spawn** — launch the detached runtime, only if half 1 passed.

Preflight is an **HTTP health probe** to the same host:port the runtime will use. It runs
as a new in-container CLI command, since `vibing` is installed by the end of half 1.

Surfacing is **log-only**: a failed preflight leaves the runtime `disconnected` (no new
state, no schema change — consistent with ADR-0017's deliberate choice that the state
label stays coarse and the logs disambiguate) and writes a clear line to the unified log,
already streamed live by ADR-0018's Logs dialog.

## Scope

Backend (`vibing_api`) + runtime CLI (`vibing_devcontainer_runtime`, `vibing_cli`) only.
No API schema, runtime-state model, or frontend change.

## Design

### 1. `vibing runtime preflight --control-plane-url <ws-url>`

New command. Lives in `vibing_devcontainer_runtime` (it is the companion's concern),
wired as a **sibling** of `vibing runtime devcontainer` under `runtime_app` in
`vibing_cli`. Chosen over nesting it under `devcontainer` because that command is a
callback with a required `--devcontainer-id`, which a subcommand would inherit and demand.

Stdlib only (`urllib.request`), no new dependency. Behaviour:

- Derive the health URL from the **same resolved WS URL** the runtime will connect to:
  scheme `ws`→`http` / `wss`→`https`; replace the path suffix `/runtime/agent/ws` with
  `/health` (so `/api/v1/runtime/agent/ws` → `/api/v1/health`); host and port preserved.
- `GET` it with a ~5s timeout, single attempt (no retry).
- HTTP 200 → print a short ok line, exit `0`.
- Connection refused / timeout / non-200 → print
  `PREFLIGHT FAILED: control plane unreachable at <health-url>: <reason>` to stderr,
  exit non-zero.

Probing the exact host:port the runtime resolves to is what catches the IP-guess failure
that is invisible today.

### 2. `RuntimeInjector.inject()` becomes two halves

`inject()` computes the resolved `agent_url` once and passes it to both halves:

```
agent_url = resolve_runtime_control_plane_url(self._runtime_url)
if not await self._bootstrap(devcontainer_id, container_id, local_path, agent_url):
    return False
return await self._spawn(devcontainer_id, local_path, agent_url)
```

**`_bootstrap`** — `docker cp` uv, `docker cp` wheel, then one `devcontainer exec`:

```bash
set -e -o pipefail
<UV_DEST> tool install --python 3.13 --from <wheel> vibing 2>&1 | tee /tmp/vibing-runtime.log
export PATH="$HOME/.local/bin:$PATH"
vibing runtime preflight --control-plane-url <agent_url> 2>&1 | tee -a /tmp/vibing-runtime.log
```

Non-zero exit (install **or** preflight, via `set -e -o pipefail`) → returns `False`.
The first `tee` truncates the log (fresh per inject); preflight appends with `tee -a`.

**`_spawn`** — a **separate** `devcontainer exec`, issued only when `_bootstrap` succeeded:

```bash
export PATH="$HOME/.local/bin:$PATH"
nohup vibing runtime devcontainer --control-plane-url <agent_url> --devcontainer-id <id> >>/tmp/vibing-runtime.log 2>&1 &
echo $! >/tmp/vibing-runtime.pid
```

`inject()` keeps its `bool` contract (True = runtime launched). `RuntimeService.inject`,
the `launching` transient, and its ~30s timeout are unchanged: a failed preflight returns
`False` exactly like a failed bootstrap does today, clearing `launching` → `disconnected`.

### 3. The unified log tells the story

The log accumulates install output → preflight result → (only if reached) runtime output.
On preflight failure the user opens the live Logs dialog and sees the `PREFLIGHT FAILED`
line with nothing spawned below it.

## Testing

- **preflight command**: URL derivation (`ws`→`http`, path swap, `wss`→`https`, port
  preserved); HTTP 200 → exit 0; connection-refused / timeout / non-200 → exit non-zero
  with the message. Monkeypatch `urllib.request.urlopen`.
- **injector**: fake runner records issued commands. Assert the spawn exec is **not**
  issued when the bootstrap exec returns non-zero; happy path issues both, in order, with
  the same `agent_url` in the preflight and the launch.
- **docs coherence**: ADR-0017 amendment note (inject is two-phase; preflight gates
  spawn), `CONTEXT.md` Runtime-lifecycle, `vibing_api/CLAUDE.md`,
  `vibing_devcontainer_runtime/CLAUDE.md`.

## Non-goals

- No distinct `bootstrap_failed` / `unreachable` runtime state (ADR-0017 rejected
  disconnected sub-states; logs disambiguate).
- No preflight retry/backoff — a single timed GET; the user re-injects if it was transient.
- No idempotent/cached bootstrap so relaunch skips reinstall — out of scope here.
