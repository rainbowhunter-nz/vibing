# Runtime `error` state: surface a failed inject in the indicator

## Problem

A failed inject — bootstrap install error or a failed preflight (control plane
unreachable from inside the container) — leaves `RuntimeService.inject()` returning
`False`, which **clears** the `launching` transient and falls back to `disconnected`.
The just-completed two-phase preflight writes the reason to the runtime log, but the
runtime *indicator* shows the same grey `disconnected` as a never-injected runtime. The
user cannot tell "I tried to launch and it failed" from "I never launched" without
opening the log.

We want a failed inject to surface as a distinct `error` state in the indicator, and the
Inject button — already shown for every non-connected state — to retry, returning the
indicator to `launching`.

## Decision

Add a 4th `RuntimeState`: `error`. It is a **sticky transient** — unlike `launching`
(cleared by WS-connect or the ~30s timeout), `error` persists until the user acts.

Scope of `error` is the **synchronous inject failure only** (`inject() == False`: bootstrap
install **or** preflight). The post-spawn **launch timeout** (runtime spawned but never
connected back within ~30s) stays `disconnected`, unchanged. Rationale: `error` means "the
synchronous half failed, nothing spawned"; the timeout is a different, asynchronous failure
and keeping it coarse avoids reclassifying the spawned-but-silent case.

This amends ADR-0017, which deliberately rejected `disconnected` sub-states. We add exactly
**one** state — `error` — for the synchronous inject failure. The `disconnected` catch-all
stays coarse (never-injected, stopped, crashed, launch-timed-out), and *why* an inject
failed still lives in the log, not in a DTO field (consistent with the log-only surfacing
of the preflight design).

## Design

### Backend

**`core/vocabularies.py`** — add `ERROR = auto()` to `RuntimeState`
(`connected | launching | disconnected | error`).

**`core/runtime_status_resolver.py`** — connected still wins so a stale `error` never masks
a live runtime:

```python
def resolve_runtime_state(transient: RuntimeState | None, connected: bool) -> RuntimeState:
    if connected:
        return RuntimeState.CONNECTED
    if transient == RuntimeState.LAUNCHING:
        return RuntimeState.LAUNCHING
    if transient == RuntimeState.ERROR:
        return RuntimeState.ERROR
    return RuntimeState.DISCONNECTED
```

**`core/runtime_service.py`** — the one behavioral change. On inject failure, set the
transient to `error` instead of clearing it:

```python
launched = await self._injector.inject_by_path(devcontainer_id, local_path)
if not launched:
    self._live.set_runtime_transient(devcontainer_id, RuntimeState.ERROR)
    self._publish(devcontainer_id)
    return
```

Everything else is untouched:
- `inject()` still sets `LAUNCHING` first thing → retry overwrites `error` with `launching`.
- `_expire_launching` still clears the transient → `disconnected` on timeout.
- `stop()` still clears the transient → `disconnected`.
- WS-connect (`runtime.py` register) still clears the transient (cannot fire post-failure,
  but the clear keeps the invariant that a connected runtime has no transient).

`error` is cleared by: a retry inject (overwrites with `launching`), `stop-runtime` (clears),
or a WS-connect (clears). It survives a plain container stop — harmless: the Inject control
is disabled while the container is not running.

No API schema change: `RuntimeConnection.state` is already a `RuntimeState`, so `error`
flows through `DevcontainerView.runtime.state` automatically.

### Frontend

**`lib/api/types.ts`** — extend the union:
`export type RuntimeState = 'connected' | 'launching' | 'disconnected' | 'error'`.

**`routes/DevcontainerDetail.tsx`** (`RuntimeSection`):
- `RUNTIME_LABEL.error = 'Error'`.
- Dot colour: `error` → `bg-bad` (the existing error red), alongside `connected` (`bg-ok`),
  `launching` (`bg-accent`), else `bg-text-subtle`.
- The Inject button already renders for every non-connected state, so it appears in `error`
  and pressing it re-injects → `launching`. No control-flow change.

**`mock/state/devcontainers.ts`** — allow an `error` runtime state in the mock store so the
indicator is inspectable via the mock scenarios, consistent with the existing
`connected | launching | disconnected` mock values.

### Logs-only reason (unchanged)

The state stays coarse `error`; the reason (the `PREFLIGHT FAILED:` line, or the install
error) is in the runtime log, already streamed live by the Logs dialog. No message field on
the DTO.

## Testing

- **resolver**: `error` transient (not connected) → `ERROR`; connected wins over an `error`
  transient → `CONNECTED`.
- **service**: inject-fail sets the `error` transient (asserts `set_runtime_transient(..,
  ERROR)`, not a clear); a retry `inject()` sets `launching` (overwrites `error`); `stop()`
  clears → `disconnected`.
- **frontend**: `RuntimeSection` with `state: 'error'` renders the "Error" label, the
  `bg-bad` dot, and a visible Inject button (clicking it calls `onAction('inject')`).
- **mock**: an `error`-runtime scenario renders the error indicator.

## Non-goals

- No `error` message/reason field on the DTO — the log carries the reason (log-only
  surfacing, consistent with the preflight design).
- No reclassifying the launch **timeout** to `error` — it stays `disconnected`.
- No auto-retry — the user re-injects manually.
- No clearing `error` on container stop/teardown — it is harmless and the Inject control is
  already gated on a running container.
