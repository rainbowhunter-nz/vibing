# VIB-17 — Frontend loading / empty / error state patterns

**Jira:** VIB-17 (Story, epic VIB-1 Product Foundation)
**Date:** 2026-05-29
**Status:** Design approved

## Problem

Foundation screens hand-roll their own loading and error UI. `Devcontainers.tsx` and
`Settings.tsx` each carry a local `State` union, a `useEffect` fetch, and copy-pasted
markup for "Loading …" and "Couldn't load … / Check that the backend is running". Only
`EmptyState` is shared. `useApiQuery` already models `loading | ready | error` but no
screen uses it. Result: ~40 lines of duplicated state markup and drifting error copy.

## Goal

Shared, visual-only loading / empty / error patterns that Devcontainers and Settings
both consume, plus a single source of truth for error copy. No runtime workflows.

## Scope

**In:**
- Shared presentational components for loading, empty, error.
- A `QueryBoundary` that dispatches on `useApiQuery`'s `QueryState`.
- Refactor `Devcontainers.tsx` and `Settings.tsx` onto `useApiQuery` + `QueryBoundary`.
- Error-copy template + written guidance.
- Tests for the components, the boundary, and the two refactored screens.

**Out (non-goals from the ticket):**
- Live session output, inbox / approval queue workflows, devcontainer runtime actions.
- A dedicated `/diagnostics` route — diagnostics stays a section inside Settings.
- Any wired action on the error state (e.g. Retry) — states are visual-only.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deliverable | Components + refactor + copy | Removes existing duplication, not just adds primitives. |
| Diagnostics | Stays a Settings section | Matches current code; no scope creep. |
| Consumption API | `QueryBoundary` + presentational components | Kills the per-screen state switch boilerplate. |
| Loading style | Centered spinner | Clear "working" signal; uniform across screens. |
| Error state | Text-only, red icon, no action | Strictly visual-only per ticket. |
| Empty state | Screen's responsibility (inside `ready`) | Emptiness is data-dependent, not a query state. |
| Copy | `loadError(subject)` factory + rules as doc-comment | One template, enforces shape, scales. |

## Components (`apps/web/src/components/`)

```
StateMessage.tsx   shared centered layout: icon chip · title · helper · tone
  EmptyState.tsx   preset tone="muted" (existing component, refactored to delegate)
  ErrorState.tsx   preset tone="error" + default warning icon
LoadingState.tsx   centered spinner + optional label
QueryBoundary.tsx  dispatches on QueryState<T>
```

### `StateMessage`
Props: `{ icon: ReactNode; title: string; helper: string; tone?: 'muted' | 'error' }`.
The existing `EmptyState` markup (centered, max-w-320, icon chip + title + helper).
`tone` switches the icon-chip class: `bg-surface-muted text-accent` (muted) vs
`bg-red-100 text-bad` (error).

### `EmptyState`
Kept as the public name (ACs reference it). Thin wrapper over `StateMessage` with
`tone="muted"`. Existing call sites (`Devcontainers`) unchanged.

### `ErrorState`
Props: `{ title: string; helper: string; icon?: ReactNode }`. Defaults `icon` to a red
warning triangle, passes `tone="error"`. No action/retry slot.

### `LoadingState`
Props: `{ label?: string }`. Centered CSS spinner (`animate-spin`, accent top-border)
above an optional muted label. Same centered frame as `StateMessage`.

### `QueryBoundary<T>`
```ts
interface QueryBoundaryProps<T> {
  state: QueryState<T>
  loading?: ReactNode   // defaults to <LoadingState />
  error?: ReactNode     // defaults to <ErrorState /> with generic copy
  children: (data: T) => ReactNode
}
```
- `state.kind === 'loading'` → `loading ?? <LoadingState />`
- `state.kind === 'error'`   → `error ?? <ErrorState … />`
- `state.kind === 'ready'`   → `children(state.data)`

Empty is **not** handled here — the `ready` branch decides (empty list vs. content).

## Copy (`apps/web/src/lib/copy.ts`)

```ts
// Error copy guidance:
//  - title:  name what failed in plain words — no jargon, no blame, no codes.
//  - helper: one actionable next step.
//  - tone:   calm, factual, sentence case, no exclamation marks.
//  - empty ≠ error: empty = "nothing here yet" + how to populate;
//                   error = "something went wrong" + how to recover.
export const loadError = (subject: string) => ({
  title: `Couldn't load ${subject}`,
  helper: 'Check that the backend is running, then reload the page.',
})
```

Screens spread it into `ErrorState`: `<ErrorState {...loadError('devcontainers')} />`.

## Screen refactor & data flow

`PageHeader` stays outside the boundary so it renders in every state.

**`Devcontainers.tsx`**
```tsx
const { state } = useApiQuery(fetchDevcontainers, [])
const crumbs = state.kind === 'ready' ? countLabel(state.data.items.length) : undefined
return (
  <>
    <PageHeader title="Devcontainers" crumbs={crumbs} />
    <div className="flex-1 overflow-auto">
      <QueryBoundary state={state} error={<ErrorState {...loadError('devcontainers')} />}>
        {(data) => data.items.length === 0
          ? <EmptyState icon={folderIcon} title="No devcontainers yet"
                        helper="Devcontainers will appear here once you add a local folder." />
          : <DevcontainerTable items={data.items} />}
      </QueryBoundary>
    </div>
  </>
)
```
Existing header-row + row JSX moves verbatim into the `ready` branch (optionally
extracted as a local `DevcontainerTable`). Local `State` union and `useEffect` deleted.

**`Settings.tsx`** — combine the two fetches into one query so the boundary has a single state:
```tsx
const { state } = useApiQuery(
  () => Promise.all([fetchSettings(), fetchDiagnostics()])
    .then(([settings, diagnostics]) => ({ settings, diagnostics })), [])
```
Wrap sections in `<QueryBoundary state={state} error={<ErrorState {...loadError('settings')} />}>`.
Diagnostics stays a section in the `ready` branch (no empty state — always has content).
Preference `useState`s (notifications, theme, …) stay as-is.

## Testing

Vitest + Testing Library, co-located in `src/components/__tests__/`. Build components
test-first (red → green) per the `tdd` skill, then refactor screens against their tests.

- **StateMessage** — renders title/helper; correct icon-chip class per `tone`.
- **EmptyState** — still renders icon/title/helper (guards the delegate refactor).
- **ErrorState** — renders title/helper; default warning icon when none passed; error tone.
- **LoadingState** — renders spinner + optional label.
- **QueryBoundary** — loading → loading slot; error → error slot; ready → `children(data)`.
- **copy** — `loadError('x')` returns expected `{ title, helper }`.
- **Devcontainers / Settings** — mock api endpoints, assert each of loading / error /
  ready(+empty) renders the right component. Backfills currently-absent route coverage.

## Acceptance criteria mapping

| AC | Covered by |
|----|-----------|
| Reusable loading pattern | `LoadingState` + `QueryBoundary` |
| Reusable empty pattern | `EmptyState` (now delegating to `StateMessage`) |
| Reusable error pattern | `ErrorState` + `QueryBoundary` |
| Same pattern on workspace list / settings / diagnostics | Devcontainers + Settings (incl. its diagnostics section) refactored |
| Copy guidance for error messages | `copy.ts` factory + doc-comment rules |
| Visual-only, no runtime workflows | No wired actions; only read-fetch + presentation |
