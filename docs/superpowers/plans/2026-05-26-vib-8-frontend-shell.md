# VIB-8 Frontend Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React app shell with sidebar + content + activity rail, five route placeholders with empty states, and a live backend-status panel that surfaces `/api/v1/health` and `/api/v1/config`.

**Architecture:** Tailwind v4 design tokens drive a flat Warm Zinc + Amber palette. React Router v7 in library mode renders an `AppShell` layout with five child routes. A single stateful component (`RailBackend`) fetches health + config once on mount; everything else is presentational.

**Tech Stack:** React 19, Vite 8, TypeScript, React Router 7, Tailwind CSS 4 (`@tailwindcss/vite`), `clsx` + `tailwind-merge` + `class-variance-authority` utilities.

**Spec:** [`docs/superpowers/specs/2026-05-26-vib-8-frontend-shell-design.md`](../specs/2026-05-26-vib-8-frontend-shell-design.md)

---

## Notes for the implementer

- All paths below are absolute from the repo root.
- Run all `pnpm` commands from `apps/web/` unless stated otherwise.
- The backend is at `http://localhost:8000` and `vite.config.ts` already proxies `/api/v1/*`. Don't change that.
- The project uses `pnpm` (Corepack). To start the backend in a second terminal: `cd apps/api && uv run uvicorn vibing_api.main:app --reload --host 127.0.0.1 --port 8000`.
- TypeScript is strict: `verbatimModuleSyntax: true` (use `import type` for type-only imports), `noUnusedLocals: true`, `erasableSyntaxOnly: true` (interfaces and types only — no `enum`, no parameter properties).
- This plan does **not** set up a JS test runner. The spec opts out: only the `pnpm build` and `pnpm lint` gates plus manual smoke verify the shell. The shell has no behaviour worth a unit test.
- Commit at the end of each task. Use the message in each task's final step verbatim (adjust nothing).

---

## Task 1: Add dependencies and wire the Tailwind v4 Vite plugin

**Files:**
- Modify: `apps/web/package.json` (via `pnpm add`)
- Modify: `apps/web/vite.config.ts`

- [ ] **Step 1: Install runtime + utility deps**

Run from `apps/web/`:

```bash
pnpm add react-router tailwindcss @tailwindcss/vite clsx tailwind-merge class-variance-authority
```

Expected: pnpm installs the six packages and updates `package.json` + `pnpm-lock.yaml`.

- [ ] **Step 2: Wire the Tailwind plugin into Vite**

Replace `apps/web/vite.config.ts` with:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 3: Verify the build still passes**

Run from `apps/web/`:

```bash
pnpm build
```

Expected: `tsc -b` succeeds, then `vite build` succeeds. (The current `App.tsx` still exists at this point, so build artifacts are non-empty; that's fine.)

- [ ] **Step 4: Commit**

```bash
git add apps/web/package.json apps/web/pnpm-lock.yaml apps/web/vite.config.ts
git commit -m "VIB-8 Add Tailwind v4 and React Router v7 deps"
```

---

## Task 2: Replace `index.css` with Tailwind base + palette tokens

**Files:**
- Modify: `apps/web/src/index.css` (full replacement)

- [ ] **Step 1: Write the new `index.css`**

Overwrite `apps/web/src/index.css` with:

```css
@import "tailwindcss";

@theme {
  --color-bg: #ffffff;
  --color-surface-sidebar: #f6f5f3;
  --color-surface-rail: #fafaf9;
  --color-surface-muted: #f4f1eb;
  --color-border: #e7e5e0;
  --color-text: #1c1917;
  --color-text-muted: #78716c;
  --color-text-subtle: #a8a29e;
  --color-accent: #d97706;
  --color-accent-bg: #fdf4e3;
  --color-ok: #16a34a;
  --color-bad: #dc2626;

  --font-sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

html, body, #root {
  height: 100%;
}

body {
  margin: 0;
  background: var(--color-bg);
  color: var(--color-text-muted);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

The `@theme` block makes utilities like `bg-surface-sidebar`, `text-accent`, `border-border` available throughout the app.

- [ ] **Step 2: Verify the build still passes**

Run from `apps/web/`:

```bash
pnpm build
```

Expected: succeeds. The compiled CSS now contains Tailwind reset + the theme tokens.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/index.css
git commit -m "VIB-8 Replace index.css with Tailwind base and warm-zinc palette"
```

---

## Task 3: Create `lib/cn.ts` and `lib/api.ts`

**Files:**
- Create: `apps/web/src/lib/cn.ts`
- Create: `apps/web/src/lib/api.ts`

- [ ] **Step 1: Create `lib/cn.ts`**

Write `apps/web/src/lib/cn.ts`:

```ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 2: Create `lib/api.ts`**

Write `apps/web/src/lib/api.ts`:

```ts
export interface HealthResponse {
  status: string
  service: string
}

export interface ConfigResponse {
  app_name: string
  api_v1_prefix: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    throw new Error(`${path} ${res.status}`)
  }
  return (await res.json()) as T
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/v1/health')
}

export function fetchConfig(): Promise<ConfigResponse> {
  return getJson<ConfigResponse>('/api/v1/config')
}
```

Shapes mirror the Pydantic models at `apps/api/src/vibing_api/api/routes/health.py` and `config.py`.

- [ ] **Step 3: Type-check**

Run from `apps/web/`:

```bash
pnpm tsc -b
```

Expected: no errors. (`pnpm build` would also work but is slower.)

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/cn.ts apps/web/src/lib/api.ts
git commit -m "VIB-8 Add cn helper and typed health/config fetchers"
```

---

## Task 4: Build presentational components (`EmptyState`, `PageHeader`, `Sidebar`, `RailActivity`)

**Files:**
- Create: `apps/web/src/components/EmptyState.tsx`
- Create: `apps/web/src/components/PageHeader.tsx`
- Create: `apps/web/src/components/Sidebar.tsx`
- Create: `apps/web/src/components/RailActivity.tsx`

- [ ] **Step 1: Create `EmptyState.tsx`**

Write `apps/web/src/components/EmptyState.tsx`:

```tsx
import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  helper: string
}

export function EmptyState({ icon, title, helper }: EmptyStateProps) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-[320px] text-center">
        <div className="mx-auto mb-3.5 flex h-10 w-10 items-center justify-center rounded-[10px] bg-surface-muted text-accent">
          {icon}
        </div>
        <h2 className="mb-1.5 text-[15px] font-semibold text-text">{title}</h2>
        <p className="text-[13px] text-text-muted">{helper}</p>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `PageHeader.tsx`**

Write `apps/web/src/components/PageHeader.tsx`:

```tsx
interface PageHeaderProps {
  title: string
  crumbs?: string
}

export function PageHeader({ title, crumbs }: PageHeaderProps) {
  return (
    <header className="border-b border-border px-6 py-3.5">
      <h1 className="text-lg font-semibold tracking-tight text-text">{title}</h1>
      {crumbs && <div className="mt-0.5 text-[11px] text-text-muted">{crumbs}</div>}
    </header>
  )
}
```

- [ ] **Step 3: Create `Sidebar.tsx`**

Write `apps/web/src/components/Sidebar.tsx`:

```tsx
import { NavLink } from 'react-router'
import { cn } from '../lib/cn'

const ITEMS = [
  { to: '/workspaces', label: 'Workspaces' },
  { to: '/inbox', label: 'Inbox' },
  { to: '/approvals', label: 'Approvals' },
  { to: '/settings', label: 'Settings' },
] as const

export function Sidebar() {
  return (
    <aside className="flex w-[200px] flex-col border-r border-border bg-surface-sidebar py-4">
      <div className="px-[18px] pb-[18px] text-[15px] font-semibold tracking-tight text-text">
        Vibing
      </div>
      <nav className="flex flex-col">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'border-l-2 border-transparent px-[18px] py-2 text-[13px] text-text-muted',
                isActive && 'border-l-accent bg-accent-bg font-medium text-text',
              )
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
```

No count badges in VIB-8 — that's a later ticket.

- [ ] **Step 4: Create `RailActivity.tsx`**

Write `apps/web/src/components/RailActivity.tsx`:

```tsx
export function RailActivity() {
  return (
    <section>
      <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        Activity
      </h3>
      <p className="text-[12px] text-text-subtle">No active agents yet.</p>
    </section>
  )
}
```

- [ ] **Step 5: Type-check**

Run from `apps/web/`:

```bash
pnpm tsc -b
```

Expected: no errors. (These components are not yet imported anywhere — they compile in isolation.)

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/EmptyState.tsx apps/web/src/components/PageHeader.tsx apps/web/src/components/Sidebar.tsx apps/web/src/components/RailActivity.tsx
git commit -m "VIB-8 Add presentational shell components"
```

---

## Task 5: Build `RailBackend` (the only stateful component)

**Files:**
- Create: `apps/web/src/components/RailBackend.tsx`

- [ ] **Step 1: Create `RailBackend.tsx`**

Write `apps/web/src/components/RailBackend.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { fetchConfig, fetchHealth, type ConfigResponse } from '../lib/api'
import { cn } from '../lib/cn'

type State =
  | { kind: 'loading' }
  | { kind: 'ok'; config: ConfigResponse }
  | { kind: 'error' }

export function RailBackend() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchHealth(), fetchConfig()])
      .then(([, config]) => {
        if (!cancelled) setState({ kind: 'ok', config })
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  const dotClass =
    state.kind === 'ok'
      ? 'bg-ok'
      : state.kind === 'error'
        ? 'bg-bad'
        : 'bg-text-subtle'
  const statusText =
    state.kind === 'ok'
      ? 'Connected'
      : state.kind === 'error'
        ? 'Unreachable'
        : 'Checking…'

  return (
    <section>
      <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        Backend
      </h3>
      <div className="mb-1.5 flex items-center gap-2 text-[12px] text-text-muted">
        <span className={cn('h-2 w-2 rounded-full', dotClass)} />
        {statusText}
      </div>
      {state.kind === 'ok' && (
        <>
          <div className="ml-4 text-[11px] text-text-subtle">service: {state.config.app_name}</div>
          <div className="ml-4 text-[11px] text-text-subtle">api: {state.config.api_v1_prefix}</div>
        </>
      )}
      {state.kind === 'error' && (
        <div className="ml-4 text-[11px] text-text-subtle">service: unavailable</div>
      )}
    </section>
  )
}
```

Behaviour per spec: parallel fetch on mount, green dot + service/api lines on success, red dot + "service: unavailable" on either failure, no retry/polling.

- [ ] **Step 2: Type-check**

Run from `apps/web/`:

```bash
pnpm tsc -b
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/RailBackend.tsx
git commit -m "VIB-8 Add RailBackend with live health/config status"
```

---

## Task 6: Build `AppShell` layout

**Files:**
- Create: `apps/web/src/routes/AppShell.tsx`

- [ ] **Step 1: Create `AppShell.tsx`**

Write `apps/web/src/routes/AppShell.tsx`:

```tsx
import { Outlet } from 'react-router'
import { Sidebar } from '../components/Sidebar'
import { RailActivity } from '../components/RailActivity'
import { RailBackend } from '../components/RailBackend'

export function AppShell() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
      <aside className="flex w-[240px] flex-col gap-4 border-l border-border bg-surface-rail p-4">
        <RailActivity />
        <div className="flex-1" />
        <RailBackend />
      </aside>
    </div>
  )
}
```

The `flex-1` spacer pushes `RailBackend` to the bottom of the rail.

- [ ] **Step 2: Type-check**

Run from `apps/web/`:

```bash
pnpm tsc -b
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/routes/AppShell.tsx
git commit -m "VIB-8 Add AppShell three-column layout"
```

---

## Task 7: Build the five route components

**Files:**
- Create: `apps/web/src/routes/Workspaces.tsx`
- Create: `apps/web/src/routes/WorkspaceDetail.tsx`
- Create: `apps/web/src/routes/Inbox.tsx`
- Create: `apps/web/src/routes/Approvals.tsx`
- Create: `apps/web/src/routes/Settings.tsx`

Each route file follows the same pattern: header + an empty state with an inline SVG icon. The icons below are Lucide-style stroke SVGs — inlined to avoid an icon-library install. No need to factor them out; each route uses its icon exactly once.

- [ ] **Step 1: Create `Workspaces.tsx`**

Write `apps/web/src/routes/Workspaces.tsx`:

```tsx
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
)

export function Workspaces() {
  return (
    <>
      <PageHeader title="Workspaces" crumbs="0 workspaces" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="No workspaces yet"
          helper="Your isolated development environments will appear here."
        />
      </div>
    </>
  )
}
```

- [ ] **Step 2: Create `WorkspaceDetail.tsx`**

Write `apps/web/src/routes/WorkspaceDetail.tsx`:

```tsx
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <path d="M12 18h.01" />
    <path d="M12 11v3" />
  </svg>
)

export function WorkspaceDetail() {
  return (
    <>
      <PageHeader title="Workspace" crumbs="Detail" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="Workspace not found"
          helper="This workspace doesn't exist or hasn't been created yet."
        />
      </div>
    </>
  )
}
```

- [ ] **Step 3: Create `Inbox.tsx`**

Write `apps/web/src/routes/Inbox.tsx`:

```tsx
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
  </svg>
)

export function Inbox() {
  return (
    <>
      <PageHeader title="Inbox" crumbs="All workspaces" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="Inbox is empty"
          helper="Questions, approval requests, failures and completions from your agent sessions will appear here."
        />
      </div>
    </>
  )
}
```

- [ ] **Step 4: Create `Approvals.tsx`**

Write `apps/web/src/routes/Approvals.tsx`:

```tsx
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <path d="m9 11 3 3L22 4" />
  </svg>
)

export function Approvals() {
  return (
    <>
      <PageHeader title="Approvals" crumbs="Pending" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="No pending approvals"
          helper="Actions Claude Code asks permission for will queue here for your decision."
        />
      </div>
    </>
  )
}
```

- [ ] **Step 5: Create `Settings.tsx`**

Write `apps/web/src/routes/Settings.tsx`:

```tsx
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

export function Settings() {
  return (
    <>
      <PageHeader title="Settings" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="Settings coming soon"
          helper="Preferences for Vibing will live here."
        />
      </div>
    </>
  )
}
```

- [ ] **Step 6: Type-check**

Run from `apps/web/`:

```bash
pnpm tsc -b
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/routes/Workspaces.tsx apps/web/src/routes/WorkspaceDetail.tsx apps/web/src/routes/Inbox.tsx apps/web/src/routes/Approvals.tsx apps/web/src/routes/Settings.tsx
git commit -m "VIB-8 Add five route placeholders with empty states"
```

---

## Task 8: Wire the router, replace `main.tsx`, delete legacy files

**Files:**
- Create: `apps/web/src/routes/router.tsx`
- Modify: `apps/web/src/main.tsx` (full replacement)
- Delete: `apps/web/src/App.tsx`
- Delete: `apps/web/src/App.css`

- [ ] **Step 1: Create `routes/router.tsx`**

Write `apps/web/src/routes/router.tsx`:

```tsx
import { createBrowserRouter, redirect } from 'react-router'
import { AppShell } from './AppShell'
import { Workspaces } from './Workspaces'
import { WorkspaceDetail } from './WorkspaceDetail'
import { Inbox } from './Inbox'
import { Approvals } from './Approvals'
import { Settings } from './Settings'

export const router = createBrowserRouter([
  {
    path: '/',
    Component: AppShell,
    children: [
      { index: true, loader: () => redirect('/workspaces') },
      { path: 'workspaces', Component: Workspaces },
      { path: 'workspaces/:id', Component: WorkspaceDetail },
      { path: 'inbox', Component: Inbox },
      { path: 'approvals', Component: Approvals },
      { path: 'settings', Component: Settings },
      { path: '*', loader: () => redirect('/workspaces') },
    ],
  },
])
```

- [ ] **Step 2: Replace `main.tsx`**

Overwrite `apps/web/src/main.tsx` with:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import './index.css'
import { router } from './routes/router'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
```

- [ ] **Step 3: Delete legacy `App.tsx` and `App.css`**

Run from the repo root:

```bash
rm apps/web/src/App.tsx apps/web/src/App.css
```

- [ ] **Step 4: Type-check and lint**

Run from `apps/web/`:

```bash
pnpm tsc -b && pnpm lint
```

Expected: both succeed with no errors. If `tsc -b` reports stale references to `App`, run `rm -rf node_modules/.tmp` first and re-run.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/router.tsx apps/web/src/main.tsx apps/web/src/App.tsx apps/web/src/App.css
git commit -m "VIB-8 Wire router and remove legacy App.tsx/App.css"
```

(`git add` on a deleted file stages the deletion.)

---

## Task 9: End-to-end verification

**Files:** none modified

- [ ] **Step 1: Production build**

Run from `apps/web/`:

```bash
pnpm build
```

Expected: `tsc -b` then `vite build` both succeed. No warnings about unused imports or unresolved modules.

- [ ] **Step 2: Lint**

Run from `apps/web/`:

```bash
pnpm lint
```

Expected: no errors.

- [ ] **Step 3: Start the backend (terminal 1)**

Run from the repo root:

```bash
cd apps/api && uv run uvicorn vibing_api.main:app --reload --host 127.0.0.1 --port 8000
```

Verify it boots: `curl http://localhost:8000/api/v1/health` → `{"status":"ok","service":"vibing-api"}`.

- [ ] **Step 4: Start the dev server (terminal 2)**

Run from `apps/web/`:

```bash
pnpm dev
```

Open `http://localhost:5173` in a browser.

- [ ] **Step 5: Smoke each route**

For each URL, confirm:

| URL | Active nav item | Page title | Empty-state title |
|---|---|---|---|
| `/` | Workspaces (after redirect) | Workspaces | No workspaces yet |
| `/workspaces` | Workspaces | Workspaces | No workspaces yet |
| `/workspaces/anything` | (none) | Workspace | Workspace not found |
| `/inbox` | Inbox | Inbox | Inbox is empty |
| `/approvals` | Approvals | Approvals | No pending approvals |
| `/settings` | Settings | Settings | Settings coming soon |
| `/nonsense` | Workspaces (after redirect) | Workspaces | No workspaces yet |

Also confirm: browser back/forward moves between routes, and direct URL entry (no in-app navigation first) loads the right route.

- [ ] **Step 6: Verify the Backend panel — happy path**

Look at the bottom-right of the shell:

- Green dot
- "Connected"
- "service: vibing-api"
- "api: /api/v1"

- [ ] **Step 7: Verify the Backend panel — failure path**

Stop the backend (Ctrl-C in terminal 1). Hard-reload the browser tab. Confirm:

- Red dot
- "Unreachable"
- "service: unavailable"

Restart the backend; hard-reload; confirm the green-dot state returns.

- [ ] **Step 8: Done — no commit**

Verification produces no file changes. If everything above passes, VIB-8 is complete.

---

## Done-when (matches the spec)

- `pnpm install`, `pnpm build`, `pnpm lint` all succeed.
- Each of `/`, `/workspaces`, `/workspaces/anything`, `/inbox`, `/approvals`, `/settings`, and an unknown path renders the shell with the expected active nav item and empty state.
- Browser back/forward and direct URL entry work.
- The Backend panel shows the connected state when the backend is up and the unreachable state when it is down.
- The visual matches the Warm Zinc + Amber palette and the layout in the brainstorm mockups (`.superpowers/brainstorm/.../content/final-shell.html`).
