# VIB-9 — Workspace list placeholder UI

## Context

Vibing is a local operations center for AI coding agents. The frontend is a React + Vite + TypeScript app backed by a FastAPI + SQLite service. VIB-8 shipped the app shell, navigation, and five route placeholders — including a `/workspaces` route that currently only renders an `<EmptyState>` (`apps/web/src/routes/Workspaces.tsx`).

The backend already exposes a full workspace CRUD API at `/api/v1/workspaces` (`apps/api/src/vibing_api/api/routes/workspaces.py`). VIB-9 wires the Workspaces route to that API so the list shows real persisted metadata — turning the dashboard into the start of a control center.

## Goal

Replace the static empty-state on `/workspaces` with a live, data-driven table that fetches persisted workspace metadata and renders one row per workspace, sized strictly to the ticket's acceptance criteria.

## Acceptance criteria (from VIB-9)

- Workspace list fetches persisted workspace metadata.
- Each workspace row shows name, source type, status, and last updated time.
- Empty state explains how workspaces will be added.
- Placeholder actions exist but are disabled for runtime actions not implemented yet.
- UI distinguishes metadata-only workspaces from running workspaces.

## Approach

Extend the existing typed-fetch pattern in `lib/api.ts` and keep the list, rows, and actions in a single `Workspaces.tsx` rewrite. No new component files, no new dependencies, no data-fetching library. This mirrors the established `RailBackend.tsx` pattern (a discriminated-union state machine driven by `useEffect` + `useState`).

## Data source

`GET /api/v1/workspaces` returns `WorkspaceList`:

```json
{ "items": [ { "id", "name", "local_path", "status", "created_at", "updated_at" } ] }
```

Notes from the backend schema (`apps/api/src/vibing_api/api/schemas/workspaces.py`):

- `status` is one of: `created`, `starting`, `running`, `stopping`, `stopped`, `error`, `deleted`.
- `created_at` / `updated_at` are UTC ISO-8601 strings (e.g. `2026-05-27T14:59:14.182+00:00`).
- The response does **not** include `source_type`. Per product decision, source type is out of scope for the MVP — only local folders are supported — so the UI renders a static **"Local folder"** label. No backend change.

## Visual design

Table layout (chosen over card grid in brainstorming). Matches the VIB-8 Warm Zinc + Amber palette already in `index.css`.

### Table columns

| Column | Content |
|---|---|
| Name | `workspace.name`, bold, primary text colour |
| Source | Static "Local folder" label, muted |
| Status | Coloured pill badge (see below) |
| Last Updated | Relative time from `updated_at` (e.g. "2 min ago") |
| (actions) | Right-aligned icon buttons: Start, Stop, Delete |

### Status badge colours

| Status | Badge style |
|---|---|
| `running` | Green — `bg-ok`-tinted (emerald) |
| `starting`, `stopping` | Amber — `accent`-tinted |
| `created`, `stopped` | Muted — `surface-muted` / `text-muted` |
| `error` | Red — `bad`-tinted |
| `deleted` | Muted (same as created/stopped) |

### Running vs metadata-only distinction

Workspaces whose status is `running` (or transitional `starting`/`stopping`) get a **green left border accent** (`border-l-[3px] border-ok`) on the row. Metadata-only rows (`created`, `stopped`, `error`, `deleted`) have no accent and align with the standard row padding. This is the primary "distinguishes running from metadata-only" signal, reinforced by the status badge colour.

### Placeholder actions (icon buttons, right-aligned)

| Icon | Action | State |
|---|---|---|
| ▶ play (inline SVG) | Start | Always **disabled** (dimmed, `cursor-not-allowed`) — runtime not implemented |
| ■ square (inline SVG) | Stop | Always **disabled** (dimmed, `cursor-not-allowed`) — runtime not implemented |
| 🗑 trash (inline SVG) | Delete | Renders **enabled** (red) as a placeholder; **no wired behaviour in VIB-9** |

All three icons are inlined SVGs in the Feather/Lucide style already used across the app (no icon library). Each button carries a `title` attribute for the tooltip/label.

> Delete is shown enabled to match the approved mockup, but VIB-9 does **not** wire up the `DELETE /api/v1/workspaces/{id}` call — clicking it does nothing. Wiring delete (with confirmation + optimistic refresh) is a later ticket. Start/Stop stay disabled because there is no runtime to drive them.

### Header count

`PageHeader` `crumbs` shows the live count: `"3 workspaces"` / `"1 workspace"` / `"0 workspaces"` (singular/plural handled).

### Empty state

Reuse the existing `<EmptyState>` component with the workspace folder icon. Updated helper copy to explain how workspaces will be added:

- Title: **No workspaces yet**
- Helper: **Workspaces will appear here once you add a local folder.**

### Loading & error states

Following the `RailBackend` discriminated-union pattern, `Workspaces` holds one of four states:

- `loading` — a minimal centered "Loading workspaces…" line (muted). No skeleton rows.
- `empty` (loaded, zero items) — the `<EmptyState>` above.
- `list` (loaded, ≥1 item) — the table.
- `error` — a centered message: **"Couldn't load workspaces."** with a muted sub-line. No retry button, no toast (consistent with `RailBackend`; page reload is recovery).

## Architecture

### `lib/api.ts` additions

```ts
export interface Workspace {
  id: string
  name: string
  local_path: string
  status: string
  created_at: string
  updated_at: string
}

interface WorkspaceList {
  items: Workspace[]
}

export function fetchWorkspaces(): Promise<WorkspaceList> {
  return getJson<WorkspaceList>('/api/v1/workspaces')
}
```

Shapes mirror the Pydantic models. `getJson` already throws on non-OK responses.

### `routes/Workspaces.tsx` rewrite

- `State` discriminated union: `{ kind: 'loading' } | { kind: 'list'; items: Workspace[] } | { kind: 'error' }`. (Empty is `list` with zero items — branch on `items.length === 0` to render `<EmptyState>`.)
- `useEffect` on mount calls `fetchWorkspaces()`, with the `cancelled` guard pattern from `RailBackend` to avoid setting state after unmount / strict-mode double-fire.
- Small pure helpers, local to the file:
  - `formatRelativeTime(iso: string): string` — uses the built-in `Intl.RelativeTimeFormat` to render "2 min ago" / "1 hr ago" / "3 days ago". No date library.
  - `statusBadgeClass(status: string): string` — maps status → Tailwind classes via `cn()`.
  - `isRunning(status: string): boolean` — `true` for `running`/`starting`/`stopping`; drives the row accent.
- Inlined SVG icon constants (play, square, trash) at module scope, matching the existing file convention.

### No new files

Everything lands in two files: the `api.ts` addition and the `Workspaces.tsx` rewrite. The row is simple and tightly coupled to the list; extracting a `WorkspaceRow` component now would be premature abstraction.

## Out of scope

Deliberately not in VIB-9:

- Wiring Start / Stop / Delete to any behaviour (Start/Stop have no runtime; Delete is a visual placeholder this ticket).
- Create-workspace UI / form.
- `source_type` in the API or any non-local-folder source support.
- Navigating from a row into `WorkspaceDetail` (the detail route still shows its own empty state).
- Polling, auto-refresh, websockets, or live status updates.
- Sorting, filtering, pagination, search.
- Confirmation dialogs / toasts.
- A frontend test runner — the project has none today; verification is `pnpm build` (TypeScript) + manual browser check. No vitest is added in this ticket.

## Risks and watchouts

- **Strict-mode double mount** fires the fetch twice in dev. The `cancelled` guard makes this harmless (same as `RailBackend`).
- **`Intl.RelativeTimeFormat`** is built into all modern browsers and Node — no dependency, but the helper must pick a sensible unit (seconds → minutes → hours → days) rather than always using one unit.
- **Delete looks clickable but does nothing.** This is intentional per the approved mockup, and called out so reviewers don't flag it as a missing handler. If a no-op enabled button feels wrong in review, the fallback is to disable Delete too — but the approved design keeps it enabled.
- The empty-state copy changes from VIB-8's "Your isolated development environments will appear here." to "Workspaces will appear here once you add a local folder." to satisfy the "explains how workspaces will be added" criterion.

## Done-when checklist

- `pnpm build` succeeds (TypeScript clean).
- With the backend running and **zero** workspaces, `/workspaces` shows the updated empty state and the header reads "0 workspaces".
- After creating workspaces via the API, `/workspaces` lists them: name, "Local folder", a coloured status badge, and a relative "last updated" time, with the header count matching.
- A `running` (or `starting`/`stopping`) workspace shows the green left-border accent; `created`/`stopped` rows do not.
- Start and Stop icon buttons render dimmed and disabled; the Delete icon renders enabled (and does nothing when clicked).
- With the backend stopped, `/workspaces` shows the "Couldn't load workspaces." error state.
- Visual matches the approved brainstorm mockup (`.superpowers/brainstorm/.../content/design-populated-v2.html`).
