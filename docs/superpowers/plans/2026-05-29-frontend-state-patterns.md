# Frontend State Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide shared, visual-only loading / empty / error state patterns that the Devcontainers and Settings screens consume, plus a single source of truth for error copy.

**Architecture:** A `StateMessage` layout primitive backs `EmptyState` (existing, refactored to delegate) and a new `ErrorState`. A new `LoadingState` shows a spinner. A `QueryBoundary` dispatches on `useApiQuery`'s `QueryState`. Both screens drop their hand-rolled `useState`/`useEffect` and adopt `useApiQuery` + `QueryBoundary`. Error copy comes from a `loadError(subject)` factory in `lib/copy.ts`.

**Tech Stack:** React 19, TypeScript, Tailwind v4, Vitest + Testing Library (happy-dom), `cn()` (clsx + tailwind-merge).

---

## Conventions for every task

- Tests use `globals: false` — import `describe/it/expect/vi` from `vitest` explicitly.
- Co-locate tests in a `__tests__/` subdir beside the code under test.
- Compose classNames with `cn(...)` from `src/lib/cn.ts`.
- Run all web commands from `apps/web`. Test runner: `pnpm test` (one file: `pnpm test src/path/file.test.tsx`).
- Branch is already `vib-17-frontend-state-patterns`.

## File Structure

| File | Responsibility |
|------|----------------|
| `src/components/StateMessage.tsx` (create) | Centered icon·title·helper layout with `tone`. |
| `src/components/EmptyState.tsx` (modify) | Thin wrapper over `StateMessage`, `tone="muted"`. |
| `src/components/ErrorState.tsx` (create) | Wrapper over `StateMessage`, `tone="error"` + default icon. |
| `src/components/LoadingState.tsx` (create) | Centered spinner + optional label. |
| `src/components/QueryBoundary.tsx` (create) | Dispatch on `QueryState<T>`. |
| `src/lib/copy.ts` (create) | `loadError(subject)` factory + guidance doc-comment. |
| `src/routes/Devcontainers.tsx` (modify) | Adopt `useApiQuery` + `QueryBoundary`. |
| `src/routes/Settings.tsx` (modify) | Adopt `useApiQuery` (combined fetch) + `QueryBoundary`. |

---

## Task 1: `StateMessage` layout primitive

**Files:**
- Create: `src/components/StateMessage.tsx`
- Test: `src/components/__tests__/StateMessage.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StateMessage } from '../StateMessage'

describe('StateMessage', () => {
  it('renders title and helper', () => {
    render(<StateMessage icon={<svg />} title="Title here" helper="Helper here" />)
    expect(screen.getByText('Title here')).toBeTruthy()
    expect(screen.getByText('Helper here')).toBeTruthy()
  })

  it('uses muted chip by default and error chip when tone="error"', () => {
    const { container, rerender } = render(
      <StateMessage icon={<svg />} title="t" helper="h" />,
    )
    expect(container.querySelector('.bg-surface-muted')).toBeTruthy()
    rerender(<StateMessage icon={<svg />} title="t" helper="h" tone="error" />)
    expect(container.querySelector('.bg-red-100')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/components/__tests__/StateMessage.test.tsx`
Expected: FAIL — cannot resolve `../StateMessage`.

- [ ] **Step 3: Write minimal implementation**

```tsx
import type { ReactNode } from 'react'
import { cn } from '../lib/cn'

interface StateMessageProps {
  icon: ReactNode
  title: string
  helper: string
  tone?: 'muted' | 'error'
}

const TONE_CHIP: Record<'muted' | 'error', string> = {
  muted: 'bg-surface-muted text-accent',
  error: 'bg-red-100 text-bad',
}

export function StateMessage({ icon, title, helper, tone = 'muted' }: StateMessageProps) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-[320px] text-center">
        <div
          aria-hidden="true"
          className={cn(
            'mx-auto mb-3.5 flex h-10 w-10 items-center justify-center rounded-[10px]',
            TONE_CHIP[tone],
          )}
        >
          {icon}
        </div>
        <h2 className="mb-1.5 text-[15px] font-semibold text-text">{title}</h2>
        <p className="text-[13px] text-text-muted">{helper}</p>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/components/__tests__/StateMessage.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/StateMessage.tsx src/components/__tests__/StateMessage.test.tsx
git commit -m "VIB-17: add StateMessage layout primitive"
```

---

## Task 2: Refactor `EmptyState` to delegate to `StateMessage`

**Files:**
- Modify: `src/components/EmptyState.tsx`
- Test: `src/components/__tests__/EmptyState.test.tsx`

- [ ] **Step 1: Write the failing test** (guards existing call sites keep working)

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EmptyState } from '../EmptyState'

describe('EmptyState', () => {
  it('renders icon, title and helper with muted tone', () => {
    const { container } = render(
      <EmptyState icon={<svg data-testid="icon" />} title="No items" helper="Add one" />,
    )
    expect(screen.getByText('No items')).toBeTruthy()
    expect(screen.getByText('Add one')).toBeTruthy()
    expect(screen.getByTestId('icon')).toBeTruthy()
    expect(container.querySelector('.bg-surface-muted')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/components/__tests__/EmptyState.test.tsx`
Expected: FAIL — the `.bg-surface-muted` assertion passes against current code, but keep the test; if green already, that's fine (this task is a safe refactor). Proceed to Step 3.

- [ ] **Step 3: Replace the file contents**

```tsx
import type { ReactNode } from 'react'
import { StateMessage } from './StateMessage'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  helper: string
}

export function EmptyState(props: EmptyStateProps) {
  return <StateMessage {...props} tone="muted" />
}
```

- [ ] **Step 4: Run tests to verify everything still passes**

Run: `pnpm test`
Expected: PASS (including StateMessage + EmptyState).

- [ ] **Step 5: Commit**

```bash
git add src/components/EmptyState.tsx src/components/__tests__/EmptyState.test.tsx
git commit -m "VIB-17: EmptyState delegates to StateMessage"
```

---

## Task 3: `ErrorState` component

**Files:**
- Create: `src/components/ErrorState.tsx`
- Test: `src/components/__tests__/ErrorState.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorState } from '../ErrorState'

describe('ErrorState', () => {
  it('renders title, helper, error tone and a default icon', () => {
    const { container } = render(
      <ErrorState title="Couldn't load X" helper="Try again" />,
    )
    expect(screen.getByText("Couldn't load X")).toBeTruthy()
    expect(screen.getByText('Try again')).toBeTruthy()
    expect(container.querySelector('.bg-red-100')).toBeTruthy()
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('uses a provided icon when given', () => {
    const { getByTestId } = render(
      <ErrorState title="t" helper="h" icon={<svg data-testid="custom" />} />,
    )
    expect(getByTestId('custom')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/components/__tests__/ErrorState.test.tsx`
Expected: FAIL — cannot resolve `../ErrorState`.

- [ ] **Step 3: Write minimal implementation**

```tsx
import type { ReactNode } from 'react'
import { StateMessage } from './StateMessage'

const defaultIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
)

interface ErrorStateProps {
  title: string
  helper: string
  icon?: ReactNode
}

export function ErrorState({ title, helper, icon = defaultIcon }: ErrorStateProps) {
  return <StateMessage icon={icon} title={title} helper={helper} tone="error" />
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/components/__tests__/ErrorState.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/ErrorState.tsx src/components/__tests__/ErrorState.test.tsx
git commit -m "VIB-17: add ErrorState component"
```

---

## Task 4: `LoadingState` component

**Files:**
- Create: `src/components/LoadingState.tsx`
- Test: `src/components/__tests__/LoadingState.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LoadingState } from '../LoadingState'

describe('LoadingState', () => {
  it('renders a status spinner', () => {
    render(<LoadingState />)
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('renders an optional label', () => {
    render(<LoadingState label="Loading devcontainers…" />)
    expect(screen.getByText('Loading devcontainers…')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/components/__tests__/LoadingState.test.tsx`
Expected: FAIL — cannot resolve `../LoadingState`.

- [ ] **Step 3: Write minimal implementation**

```tsx
interface LoadingStateProps {
  label?: string
}

export function LoadingState({ label }: LoadingStateProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8">
      <div
        role="status"
        aria-label="Loading"
        className="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-accent"
      />
      {label && <p className="text-[13px] text-text-muted">{label}</p>}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/components/__tests__/LoadingState.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/LoadingState.tsx src/components/__tests__/LoadingState.test.tsx
git commit -m "VIB-17: add LoadingState spinner component"
```

---

## Task 5: `copy.ts` error-copy factory

**Files:**
- Create: `src/lib/copy.ts`
- Test: `src/lib/__tests__/copy.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest'
import { loadError } from '../copy'

describe('loadError', () => {
  it('builds a titled error message for the subject', () => {
    expect(loadError('devcontainers')).toEqual({
      title: "Couldn't load devcontainers",
      helper: 'Check that the backend is running, then reload the page.',
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/lib/__tests__/copy.test.ts`
Expected: FAIL — cannot resolve `../copy`.

- [ ] **Step 3: Write minimal implementation**

```ts
// Error copy guidance:
//  - title:  name what failed in plain words — no jargon, no blame, no codes.
//  - helper: one actionable next step.
//  - tone:   calm, factual, sentence case, no exclamation marks.
//  - empty ≠ error: empty = "nothing here yet" + how to populate;
//                   error = "something went wrong" + how to recover.
export function loadError(subject: string) {
  return {
    title: `Couldn't load ${subject}`,
    helper: 'Check that the backend is running, then reload the page.',
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/lib/__tests__/copy.test.ts`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add src/lib/copy.ts src/lib/__tests__/copy.test.ts
git commit -m "VIB-17: add error-copy factory and guidance"
```

---

## Task 6: `QueryBoundary` component

**Files:**
- Create: `src/components/QueryBoundary.tsx`
- Test: `src/components/__tests__/QueryBoundary.test.tsx`

Depends on Tasks 4 and 5 (`LoadingState`, `loadError`).

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryBoundary } from '../QueryBoundary'
import type { QueryState } from '../../lib/api'

describe('QueryBoundary', () => {
  it('renders the default spinner while loading', () => {
    const state: QueryState<{ name: string }> = { kind: 'loading' }
    render(<QueryBoundary state={state}>{(d) => <span>{d.name}</span>}</QueryBoundary>)
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('renders the provided error slot on error', () => {
    const state: QueryState<{ name: string }> = { kind: 'error', error: new Error('x') }
    render(
      <QueryBoundary state={state} error={<span>boom</span>}>
        {(d) => <span>{d.name}</span>}
      </QueryBoundary>,
    )
    expect(screen.getByText('boom')).toBeTruthy()
  })

  it('renders children with data when ready', () => {
    const state: QueryState<{ name: string }> = { kind: 'ready', data: { name: 'alpha' } }
    render(<QueryBoundary state={state}>{(d) => <span>{d.name}</span>}</QueryBoundary>)
    expect(screen.getByText('alpha')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/components/__tests__/QueryBoundary.test.tsx`
Expected: FAIL — cannot resolve `../QueryBoundary`.

- [ ] **Step 3: Write minimal implementation**

```tsx
import type { ReactNode } from 'react'
import type { QueryState } from '../lib/api'
import { LoadingState } from './LoadingState'
import { ErrorState } from './ErrorState'
import { loadError } from '../lib/copy'

interface QueryBoundaryProps<T> {
  state: QueryState<T>
  loading?: ReactNode
  error?: ReactNode
  children: (data: T) => ReactNode
}

export function QueryBoundary<T>({ state, loading, error, children }: QueryBoundaryProps<T>) {
  switch (state.kind) {
    case 'loading':
      return <>{loading ?? <LoadingState />}</>
    case 'error':
      return <>{error ?? <ErrorState {...loadError('this page')} />}</>
    case 'ready':
      return <>{children(state.data)}</>
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/components/__tests__/QueryBoundary.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/QueryBoundary.tsx src/components/__tests__/QueryBoundary.test.tsx
git commit -m "VIB-17: add QueryBoundary dispatcher"
```

---

## Task 7: Refactor `Devcontainers.tsx`

**Files:**
- Modify: `src/routes/Devcontainers.tsx`
- Test: `src/routes/__tests__/Devcontainers.test.tsx`

**Refactor outline:** remove the local `State` union, `useState`, and `useEffect`. Use `useApiQuery(fetchDevcontainers, [])`. Move the existing header-row + rows JSX into a local `DevcontainerTable({ items })`. Keep the helper consts (`folderIcon`, `playIcon`, `stopIcon`, `trashIcon`, `RUNNING_STATUSES`, `isRunning`, `statusBadgeClass`, `RELATIVE_UNITS`, `relativeTimeFormat`, `formatRelativeTime`, `countLabel`, `COLUMNS`) unchanged.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { Devcontainers } from '../Devcontainers'
import { fetchDevcontainers } from '../../lib/api'

vi.mock('../../lib/api/endpoints')
const mockFetch = vi.mocked(fetchDevcontainers)

function renderPage() {
  return render(
    <MemoryRouter>
      <Devcontainers />
    </MemoryRouter>,
  )
}

beforeEach(() => vi.clearAllMocks())

const sample = {
  id: 'dc1',
  name: 'my-project',
  local_path: '/home/me/my-project',
  status: 'stopped',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

describe('Devcontainers', () => {
  it('shows the spinner while loading', () => {
    mockFetch.mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('shows the error state when the fetch rejects', async () => {
    mockFetch.mockRejectedValue(new Error('down'))
    renderPage()
    await waitFor(() => expect(screen.getByText("Couldn't load devcontainers")).toBeTruthy())
  })

  it('shows the empty state when there are no devcontainers', async () => {
    mockFetch.mockResolvedValue({ items: [] })
    renderPage()
    await waitFor(() => expect(screen.getByText('No devcontainers yet')).toBeTruthy())
  })

  it('lists devcontainers when ready', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    renderPage()
    await waitFor(() => expect(screen.getByText('my-project')).toBeTruthy())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/routes/__tests__/Devcontainers.test.tsx`
Expected: FAIL — error/empty assertions fail against the current hand-rolled copy and `vi.mock` of endpoints is not yet wired to the new code path. (Current error copy is "Couldn't load devcontainers" already, but loading uses text not a `status` role — so the first test fails.)

- [ ] **Step 3: Rewrite the component body**

Replace the imports block and the `Devcontainers` function. Keep everything from the `folderIcon` const down to `COLUMNS` as-is. New imports at top:

```tsx
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { fetchDevcontainers, useApiQuery, type Devcontainer } from '../lib/api'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'
```

Delete the `type State = …` union (lines ~35-38 in the original). Replace the `Devcontainers` function and add `DevcontainerTable`:

```tsx
function DevcontainerTable({ items }: { items: Devcontainer[] }) {
  return (
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
      {items.map((devcontainer) => {
        const running = isRunning(devcontainer.status)
        return (
          <div
            key={devcontainer.id}
            className={cn(
              COLUMNS,
              'items-center border-b border-border px-4 py-3',
              running ? 'border-l-[3px] border-l-ok' : 'pl-[19px]',
            )}
          >
            <span className="text-[13px] font-semibold text-text">{devcontainer.name}</span>
            <span className="text-xs text-text-muted">Local folder</span>
            <span>
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-[11px] font-medium',
                  statusBadgeClass(devcontainer.status),
                )}
              >
                {devcontainer.status}
              </span>
            </span>
            <span className="text-xs text-text-muted">{formatRelativeTime(devcontainer.updated_at)}</span>
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
  )
}

export function Devcontainers() {
  const { state } = useApiQuery(fetchDevcontainers, [])
  const crumbs = state.kind === 'ready' ? countLabel(state.data.items.length) : undefined

  return (
    <>
      <PageHeader title="Devcontainers" crumbs={crumbs} />
      <div className="flex-1 overflow-auto">
        <QueryBoundary state={state} error={<ErrorState {...loadError('devcontainers')} />}>
          {(data) =>
            data.items.length === 0 ? (
              <EmptyState
                icon={folderIcon}
                title="No devcontainers yet"
                helper="Devcontainers will appear here once you add a local folder."
              />
            ) : (
              <DevcontainerTable items={data.items} />
            )
          }
        </QueryBoundary>
      </div>
    </>
  )
}
```

Remove the now-unused `useEffect`/`useState` import from `react` (no React imports remain needed in this file).

- [ ] **Step 4: Run test + typecheck**

Run: `pnpm test src/routes/__tests__/Devcontainers.test.tsx`
Expected: PASS (4 tests).
Run: `pnpm typecheck`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/routes/Devcontainers.tsx src/routes/__tests__/Devcontainers.test.tsx
git commit -m "VIB-17: Devcontainers uses useApiQuery + QueryBoundary"
```

---

## Task 8: Refactor `Settings.tsx`

**Files:**
- Modify: `src/routes/Settings.tsx`
- Test: `src/routes/__tests__/Settings.test.tsx`

**Refactor outline:** combine the two fetches into one `useApiQuery` returning `{ settings, diagnostics }`. Remove the local `State` union and the `useEffect`. Keep the preference `useState`s (notifications, displayName, theme, sidebarWidth) and all sub-components (`Section`, `Field`, `Toggle`, `DiagnosticRow`, the `STATUS_*` maps) unchanged. Wrap the body in `QueryBoundary`; `PageHeader` stays outside it.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { Settings } from '../Settings'
import { fetchSettings, fetchDiagnostics } from '../../lib/api'

vi.mock('../../lib/api/endpoints')
const mockSettings = vi.mocked(fetchSettings)
const mockDiagnostics = vi.mocked(fetchDiagnostics)

beforeEach(() => vi.clearAllMocks())

const settings = {
  backend_host: '127.0.0.1',
  backend_port: 8000,
  runtime: { docker: true, podman: null, devcontainer_cli: null, claude_code: null },
}
const diagnostics = { checks: [{ id: 'docker', label: 'Docker', status: 'ok' as const, message: null }] }

describe('Settings', () => {
  it('shows the spinner while loading', () => {
    mockSettings.mockReturnValue(new Promise(() => {}))
    mockDiagnostics.mockReturnValue(new Promise(() => {}))
    render(<Settings />)
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('shows the error state when a fetch rejects', async () => {
    mockSettings.mockRejectedValue(new Error('down'))
    mockDiagnostics.mockResolvedValue(diagnostics)
    render(<Settings />)
    await waitFor(() => expect(screen.getByText("Couldn't load settings")).toBeTruthy())
  })

  it('renders settings and diagnostics when ready', async () => {
    mockSettings.mockResolvedValue(settings)
    mockDiagnostics.mockResolvedValue(diagnostics)
    render(<Settings />)
    await waitFor(() => expect(screen.getByText('Docker')).toBeTruthy())
    expect(screen.getByDisplayValue('127.0.0.1')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/routes/__tests__/Settings.test.tsx`
Expected: FAIL — loading uses text, not a `status` role.

- [ ] **Step 3: Rewrite imports and the data-fetching path**

New imports at top (replace the `useEffect, useState, type ReactNode` react import and the api import):

```tsx
import { useState, type ReactNode } from 'react'
import { PageHeader } from '../components/PageHeader'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import {
  fetchDiagnostics,
  fetchSettings,
  useApiQuery,
  type DiagnosticCheck,
  type DiagnosticStatus,
  type DiagnosticsResponse,
  type SettingsResponse,
} from '../lib/api'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'
```

Delete the `type State = …` union. Replace the `Settings` function with:

```tsx
export function Settings() {
  const { state } = useApiQuery(
    () =>
      Promise.all([fetchSettings(), fetchDiagnostics()]).then(([settings, diagnostics]) => ({
        settings,
        diagnostics,
      })),
    [],
  )
  const [notifications, setNotifications] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('system')
  const [sidebarWidth, setSidebarWidth] = useState(240)

  return (
    <>
      <PageHeader title="Settings" />
      <div className="flex-1 overflow-auto">
        <QueryBoundary state={state} error={<ErrorState {...loadError('settings')} />}>
          {({ settings, diagnostics }) => (
            <>
              <Section title="Preferences">
                <p className="text-xs text-text-muted">Placeholder controls — not wired up yet.</p>
                <Field label="Enable notifications">
                  <div className="flex items-center gap-2">
                    <Toggle id="notifications-toggle" checked={notifications} onChange={setNotifications} />
                    <span className="text-[13px] text-text-muted">{notifications ? 'On' : 'Off'}</span>
                  </div>
                </Field>
                <Field label="Display name" id="display-name">
                  <input
                    id="display-name"
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="e.g. Hank"
                    className={cn(inputClass, 'max-w-[320px]')}
                  />
                </Field>
                <Field label="Theme" id="theme-select">
                  <select
                    id="theme-select"
                    value={theme}
                    onChange={(e) => setTheme(e.target.value as typeof theme)}
                    className={cn(inputClass, 'max-w-[240px]')}
                  >
                    <option value="system">System</option>
                    <option value="light">Light</option>
                    <option value="dark">Dark</option>
                  </select>
                </Field>
                <Field label="Sidebar width" id="sidebar-width">
                  <div className="flex max-w-[320px] items-center gap-3">
                    <input
                      id="sidebar-width"
                      type="range"
                      min={200}
                      max={320}
                      step={4}
                      value={sidebarWidth}
                      onChange={(e) => setSidebarWidth(Number(e.target.value))}
                      className="flex-1 accent-accent"
                    />
                    <span className="w-12 text-right text-[13px] tabular-nums text-text-muted">{sidebarWidth}px</span>
                  </div>
                </Field>
              </Section>

              <Section title="Backend">
                <Field label="Host" id="backend-host" hint="Set via environment; applies on restart.">
                  <input
                    id="backend-host"
                    type="text"
                    value={settings.backend_host}
                    readOnly
                    className={cn(readOnlyClass, 'max-w-[480px]')}
                  />
                </Field>
                <Field label="Port" id="backend-port">
                  <input
                    id="backend-port"
                    type="text"
                    value={String(settings.backend_port)}
                    readOnly
                    className={cn(readOnlyClass, 'max-w-[160px]')}
                  />
                </Field>
              </Section>

              <Section title="Diagnostics">
                <div className="space-y-2">
                  {diagnostics.checks.map((check) => (
                    <DiagnosticRow key={check.id} check={check} />
                  ))}
                </div>
              </Section>
            </>
          )}
        </QueryBoundary>
      </div>
    </>
  )
}
```

Leave `inputClass`, `readOnlyClass`, `Section`, `Field`, `Toggle`, `STATUS_DOT`, `STATUS_LABEL`, `DiagnosticRow` definitions unchanged above the component.

- [ ] **Step 4: Run test + typecheck + full suite**

Run: `pnpm test src/routes/__tests__/Settings.test.tsx`
Expected: PASS (3 tests).
Run: `pnpm typecheck && pnpm test`
Expected: no type errors; full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/routes/Settings.tsx src/routes/__tests__/Settings.test.tsx
git commit -m "VIB-17: Settings uses useApiQuery + QueryBoundary"
```

---

## Task 9: Final verification

- [ ] **Step 1: Lint, typecheck, test, build**

Run (from `apps/web`):
```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```
Expected: all pass; no unused-import lint errors in the two refactored routes.

- [ ] **Step 2: Manual sanity (optional)**

Run `pnpm dev`, visit `/devcontainers` and `/settings`. With the backend down, both show the spinner then the error state. With it up and no devcontainers, the list shows the empty state.

- [ ] **Step 3: Commit any lint fixups**

```bash
git add -A && git commit -m "VIB-17: lint/typecheck fixups"
```

---

## Self-Review notes

- **Spec coverage:** loading (Task 4 + 6), empty (Task 2), error (Task 3 + 6), same pattern on Devcontainers + Settings/diagnostics (Tasks 7-8), copy guidance (Task 5), visual-only (no actions wired anywhere). All ACs mapped.
- **Type consistency:** `loadError(subject) => { title, helper }` used identically in Tasks 5/6/7/8; `QueryState<T>` from `../lib/api` used in Tasks 6/7/8; `StateMessage` `tone` union `'muted' | 'error'` consistent across Tasks 1/2/3.
- **Endpoint return types (verified against `src/lib/api/types.ts`):** `fetchDevcontainers` → `DevcontainerList` (`{ items: Devcontainer[] }`), `Devcontainer` = `{ id, name, local_path, status, created_at, updated_at }`. `fetchSettings` → `SettingsResponse` = `{ backend_host, backend_port, runtime }`. `fetchDiagnostics` → `DiagnosticsResponse` = `{ checks: DiagnosticCheck[] }`, `DiagnosticCheck` = `{ id, label, status, message }`. Test fixtures above already match these shapes.
