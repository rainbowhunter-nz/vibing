# Runtime section on the Devcontainer detail page

## Goal

Separate runtime status/control from devcontainer lifecycle on the detail page.
Today the runtime indicator and the Inject-runtime button live in the top control
bar alongside Start/Stop/Remove. Move them into a dedicated **Runtime** section, and
show Inject as a greyed-out (disabled) button when the container isn't running
instead of hiding it — disabled state advertises the capability.

## Scope

Frontend only (`apps/web`). No API, type, or mock changes — the `inject` action and
`dc.runtime.runtime_connected` already exist. File touched:
`src/routes/DevcontainerDetail.tsx` (plus its test).

## Design

### Top bar — `LifecycleHeader`

Remove the runtime dot/label (current lines ~115–118) and the Inject icon button
(current lines ~129–133). The bar keeps: name, status badge, source badge, and the
lifecycle icons — Start/Stop and Remove. It becomes purely devcontainer lifecycle.

### New `RuntimeSection`

Rendered inside `ControlPanel`, **above** the "Coding harnesses" section (harnesses
depend on the runtime). Reuses the existing `SectionTitle`.

- Title: `Runtime`.
- One row: status on the left, Inject icon button (`InjectIcon` via `IconButton`) on
  the right (`ml-auto`), mirroring the harness section's layout.
- Status, driven by `dc.runtime.runtime_connected`:
  - connected → green dot (`bg-ok`) + `Connected`
  - not connected → grey dot (`bg-text-subtle`) + `Not connected` (muted text)

`RuntimeSection` takes the same `{ dc, busy, onAction }` props shape used by
`LifecycleHeader`, so the existing `act()` wiring in `DevcontainerDetail` is reused.
`ControlPanel` already receives `dc`; it also needs `busy` and `onAction` threaded
through from `DevcontainerDetail` to render `RuntimeSection`.

### Inject button states

| Container state | Inject button |
|---|---|
| running | enabled → `onAction('inject')` |
| running, inject in flight | spinner (`busy`) |
| not running (stopped/error/transitioning) | disabled, greyed, tooltip "Start the container to inject runtime" |

`IconButton` currently only models `busy` (spinner + `opacity-40 cursor-not-allowed`).
Add a distinct `disabled` prop so the two states read differently:

- `busy` → spinner, non-interactive.
- `disabled` → the real icon shown but greyed (`opacity-40 cursor-not-allowed`), no
  spinner, `onClick` not fired.

Inject is `disabled={!running}` and `busy={busy && running}` (spinner only for the
in-flight inject, not while greyed). Tooltip switches with state: "Inject runtime"
when enabled, "Start the container to inject runtime" when disabled.

## Testing

Update `DevcontainerDetail.test.tsx`:

- Runtime status text/dot reflects `runtime_connected`.
- Inject button is present but disabled when status is not `running`; clicking it does
  not call the inject endpoint.
- Inject is enabled and triggers inject when `running`.
- Top bar no longer renders the runtime indicator or inject control.

Run `pnpm test` and `pnpm e2e` (e2e already exercises the detail view; adjust selectors
if the inject control moved). Keep `apps/web/CLAUDE.md` coherent — its detail-view
description mentions "Inject-Runtime when running" in the icon controls; update it to
reflect the new Runtime section and always-visible (disabled-when-stopped) Inject.

## Out of scope

Helper/explanatory text in the section (Layout A is intentionally minimal), any
backend or mock changes, and changes to the harness section beyond placement order.
