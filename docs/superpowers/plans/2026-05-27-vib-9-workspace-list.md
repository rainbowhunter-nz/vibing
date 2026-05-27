# VIB-9 Workspace List Placeholder UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `/workspaces` route to the existing `GET /api/v1/workspaces` API and render persisted workspace metadata as a table, with loading/empty/error states and disabled placeholder actions.

**Architecture:** Two files change. `lib/api.ts` gains a typed `fetchWorkspaces()` wrapper (same pattern as `fetchHealth`/`fetchConfig`). `routes/Workspaces.tsx` is rewritten as a discriminated-union state machine driven by `useEffect` + `useState` (mirroring `components/RailBackend.tsx`), rendering a table of workspace rows. No new files, no new dependencies, no data-fetching library.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS v4 (palette tokens in `apps/web/src/index.css`), `react-router` v7. Backend is FastAPI + SQLite (already built).

> **Testing note:** The frontend has **no test runner** today, and the spec keeps it that way (out of scope). Verification for each task is therefore (a) `pnpm build` for TypeScript correctness and (b) a manual browser check. The build's `noUnusedLocals`/`noUnusedParameters` flags mean every commit must be self-consistent — that is why the `Workspaces.tsx` rewrite lands in a single task rather than incremental partial edits.

**Working directory:** All `pnpm` commands run from `apps/web`. All `uv`/`curl` commands run from `apps/api` (or anywhere, for curl).

---

### Task 1: Add `fetchWorkspaces()` and `Workspace` type to the API client

**Files:**
- Modify: `apps/web/src/lib/api.ts`

- [ ] **Step 1: Add the `Workspace` interface, `WorkspaceList` interface, and `fetchWorkspaces()` function**

Append to `apps/web/src/lib/api.ts` (after the existing `fetchConfig` function). The shapes mirror the Pydantic models in `apps/api/src/vibing_api/api/schemas/workspaces.py`. `getJson` already exists in this file and throws on non-OK responses.

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

- [ ] **Step 2: Verify the build passes**

Run (from `apps/web`):

```bash
pnpm build
```

Expected: build succeeds, no TypeScript errors. (`Workspace` is exported and `fetchWorkspaces` is exported, so `noUnusedLocals` does not flag them even though no consumer exists yet. `WorkspaceList` is used as the return type, so it is not flagged either.)

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): add fetchWorkspaces API client for VIB-9"
```

---

### Task 2: Rewrite the Workspaces route as a data-driven table

**Files:**
- Modify (full rewrite): `apps/web/src/routes/Workspaces.tsx`

- [ ] **Step 1: Replace the entire contents of `apps/web/src/routes/Workspaces.tsx`**

This replaces the current static-`EmptyState` version. The complete new file:

```tsx
import { useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { fetchWorkspaces, type Workspace } from '../lib/api'
import { cn } from '../lib/cn'

const folderIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
)

const playIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="5 3 19 12 5 21 5 3" />
  </svg>
)

const stopIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" />
  </svg>
)

const trashIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
)

type State =
  | { kind: 'loading' }
  | { kind: 'list'; items: Workspace[] }
  | { kind: 'error' }

const RUNNING_STATUSES = new Set(['running', 'starting', 'stopping'])

function isRunning(status: string): boolean {
  return RUNNING_STATUSES.has(status)
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-emerald-100 text-emerald-800'
    case 'starting':
    case 'stopping':
      return 'bg-accent-bg text-accent'
    case 'error':
      return 'bg-red-100 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 60 * 60 * 24 * 365],
  ['month', 60 * 60 * 24 * 30],
  ['day', 60 * 60 * 24],
  ['hour', 60 * 60],
  ['minute', 60],
  ['second', 1],
]

const relativeTimeFormat = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

function formatRelativeTime(iso: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000)
  const abs = Math.abs(seconds)
  for (const [unit, secondsPerUnit] of RELATIVE_UNITS) {
    if (abs >= secondsPerUnit || unit === 'second') {
      return relativeTimeFormat.format(Math.round(seconds / secondsPerUnit), unit)
    }
  }
  return relativeTimeFormat.format(0, 'second')
}

function countLabel(n: number): string {
  return `${n} ${n === 1 ? 'workspace' : 'workspaces'}`
}

const COLUMNS = 'grid grid-cols-[1fr_110px_100px_150px_80px]'

export function Workspaces() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetchWorkspaces()
      .then((data) => {
        if (!cancelled) setState({ kind: 'list', items: data.items })
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  const crumbs = state.kind === 'list' ? countLabel(state.items.length) : undefined

  return (
    <>
      <PageHeader title="Workspaces" crumbs={crumbs} />
      <div className="flex-1 overflow-auto">
        {state.kind === 'loading' && (
          <div className="flex h-full items-center justify-center p-8 text-[13px] text-text-muted">
            Loading workspaces…
          </div>
        )}

        {state.kind === 'error' && (
          <div className="flex h-full items-center justify-center p-8">
            <div className="max-w-[320px] text-center">
              <h2 className="mb-1.5 text-[15px] font-semibold text-text">Couldn't load workspaces</h2>
              <p className="text-[13px] text-text-muted">
                Check that the backend is running, then reload the page.
              </p>
            </div>
          </div>
        )}

        {state.kind === 'list' && state.items.length === 0 && (
          <EmptyState
            icon={folderIcon}
            title="No workspaces yet"
            helper="Workspaces will appear here once you add a local folder."
          />
        )}

        {state.kind === 'list' && state.items.length > 0 && (
          <div>
            <div
              className={cn(
                COLUMNS,
                'border-b border-border bg-surface-muted px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted',
              )}
            >
              <span>Name</span>
              <span>Source</span>
              <span>Status</span>
              <span>Last Updated</span>
              <span />
            </div>
            {state.items.map((workspace) => {
              const running = isRunning(workspace.status)
              return (
                <div
                  key={workspace.id}
                  className={cn(
                    COLUMNS,
                    'items-center border-b border-border px-4 py-3',
                    running ? 'border-l-[3px] border-l-ok' : 'pl-[19px]',
                  )}
                >
                  <span className="text-[13px] font-semibold text-text">{workspace.name}</span>
                  <span className="text-xs text-text-muted">Local folder</span>
                  <span>
                    <span
                      className={cn(
                        'rounded-full px-2 py-0.5 text-[11px] font-medium',
                        statusBadgeClass(workspace.status),
                      )}
                    >
                      {workspace.status}
                    </span>
                  </span>
                  <span className="text-xs text-text-muted">{formatRelativeTime(workspace.updated_at)}</span>
                  <div className="flex items-center justify-end gap-0.5">
                    <button
                      title="Start"
                      disabled
                      className="flex h-7 w-7 cursor-not-allowed items-center justify-center rounded-[5px] text-text-muted opacity-[0.4]"
                    >
                      {playIcon}
                    </button>
                    <button
                      title="Stop"
                      disabled
                      className="flex h-7 w-7 cursor-not-allowed items-center justify-center rounded-[5px] text-text-muted opacity-[0.4]"
                    >
                      {stopIcon}
                    </button>
                    <button
                      title="Delete"
                      className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-[5px] text-bad hover:bg-surface-muted"
                    >
                      {trashIcon}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}
```

Key behaviors this encodes (all from the spec):
- **Fetch** on mount with the `cancelled` guard (strict-mode safe, same as `RailBackend`).
- **States**: `loading` line → `error` block → `list` with zero items renders `<EmptyState>` → `list` with items renders the table.
- **Columns**: Name (bold), static "Local folder", coloured status badge, relative "last updated", right-aligned icon actions.
- **Running distinction**: `running`/`starting`/`stopping` rows get the 3px green left border; others get `pl-[19px]` so content aligns.
- **Actions**: Start (▶) and Stop (■) always `disabled` and dimmed; Delete (🗑) renders enabled/red but has **no `onClick`** — a no-op placeholder this ticket.
- **Header count**: `crumbs` shows `"N workspace(s)"` only once loaded.

- [ ] **Step 2: Verify the build passes**

Run (from `apps/web`):

```bash
pnpm build
```

Expected: build succeeds with no TypeScript errors. (Every declared helper — `isRunning`, `statusBadgeClass`, `formatRelativeTime`, `countLabel`, `COLUMNS`, the icon constants, `RUNNING_STATUSES`, `RELATIVE_UNITS`, `relativeTimeFormat` — is used, satisfying `noUnusedLocals`.)

- [ ] **Step 3: Manual browser verification**

Start the backend with a **clean temp database** so you can observe the empty state first (from `apps/api`):

```bash
cd apps/api
uv sync
VIBING_DATABASE_URL=sqlite:////tmp/vib9.db uv run uvicorn vibing_api.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend (from `apps/web`):

```bash
cd apps/web
pnpm install
pnpm dev
```

Open `http://localhost:5173/workspaces` and check, in order:

1. **Empty state** — with the clean DB and zero workspaces, the page shows the folder icon, "No workspaces yet", and "Workspaces will appear here once you add a local folder.". Header crumbs read "0 workspaces".

2. **Populated + running distinction** — seed three workspaces, then flip one to `running` (third terminal):

```bash
curl -s -X POST http://localhost:8000/api/v1/workspaces -H 'Content-Type: application/json' -d '{"name":"my-api","local_path":"/repos/my-api"}'
curl -s -X POST http://localhost:8000/api/v1/workspaces -H 'Content-Type: application/json' -d '{"name":"frontend","local_path":"/repos/frontend"}'
curl -s -X POST http://localhost:8000/api/v1/workspaces -H 'Content-Type: application/json' -d '{"name":"data-pipeline","local_path":"/repos/data-pipeline"}'
# Grab the first workspace id and mark it running:
ID=$(curl -s http://localhost:8000/api/v1/workspaces | python3 -c "import sys,json;print(json.load(sys.stdin)['items'][0]['id'])")
curl -s -X PATCH "http://localhost:8000/api/v1/workspaces/$ID" -H 'Content-Type: application/json' -d '{"status":"running"}'
```

Reload `http://localhost:5173/workspaces` and confirm:
- Three rows, each showing name, "Local folder", a status badge, and a relative time (e.g. "now"/"1 minute ago").
- The `running` row has a **green left border**; the two `created` rows do not (and their content still aligns horizontally).
- The `running` badge is green; `created` badges are muted grey.
- Header crumbs read "3 workspaces".
- Start and Stop icons are **dimmed/disabled** (cursor shows not-allowed on hover); the trash icon is **red and clickable** but clicking it does **nothing** (expected — no handler this ticket).

3. **Error state** — stop the backend process (Ctrl-C in the API terminal), then reload `http://localhost:5173/workspaces`. Confirm it shows "Couldn't load workspaces" with the helper line.

If any check fails, fix `Workspaces.tsx` and re-run Step 2 + Step 3 before committing.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/routes/Workspaces.tsx
git commit -m "feat(web): render workspace list table for VIB-9"
```

---

## Self-review notes (already reconciled)

- **Spec coverage:** Fetch (Task 1 + Task 2 `useEffect`); row columns name/source/status/last-updated (Task 2 table); empty-state copy (Task 2 `EmptyState`); disabled placeholder actions (Task 2 Start/Stop disabled, Delete no-op); running-vs-metadata distinction (Task 2 green left border + badge colour). All five acceptance criteria map to a step.
- **No backend changes:** `source_type` stays out of scope; the UI shows a static "Local folder" label.
- **Type consistency:** `Workspace` fields (`id`, `name`, `local_path`, `status`, `created_at`, `updated_at`) defined in Task 1 are exactly the ones consumed in Task 2 (`workspace.name`, `workspace.status`, `workspace.updated_at`, `workspace.id`). `fetchWorkspaces()` returns `{ items: Workspace[] }`, consumed as `data.items`.
```
