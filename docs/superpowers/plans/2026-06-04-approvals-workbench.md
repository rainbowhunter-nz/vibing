# Approvals Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder `/approvals` page with a single-column approval queue where users approve/reject pending Approval Requests inline and review approved/rejected history, with status updating live over SSE.

**Architecture:** A single React route component (`Approvals.tsx`) mirroring `Inbox.tsx`. Three status tabs each drive a server-side `listApprovalRequests({ status })` fetch via `useApiQuery`. Each pending row owns a small action state machine (idle → in-flight → "submitted, awaiting runtime") wired to the existing `resolveAgentSessionApproval` endpoint, which returns `202` without flipping status — the real `approved`/`rejected` arrives via an SSE `approvals` invalidation that triggers a refetch.

**Tech Stack:** React + TypeScript + Vite + Tailwind; Vitest + Testing Library + `userEvent`; existing `lib/api` (typed endpoints, `useApiQuery`, `ApiError`) and `lib/events` (`useSseInvalidation`).

**Ground truth (already exists — do NOT modify):**
- `listApprovalRequests({ status?, devcontainerId? })` and `resolveAgentSessionApproval(devcontainerId, sessionId, { approval_request_id, resolution })` in `src/lib/api/endpoints.ts`.
- Types `ApprovalRequest`, `ApprovalStatus` (`'pending' | 'approved' | 'rejected'`), `ApprovalResolution` (`'approved' | 'rejected'`) in `src/lib/api/types.ts`.
- The resolution endpoint returns **202** with the *unchanged* session; the stale error code is `APPROVAL_REQUEST_NOT_PENDING` (409).
- SSE scope names: `approvals`, `inbox`, `agent_sessions`.
- All of the above are re-exported from the `../lib/api` barrel.

**Working directory:** `apps/web`. Run all commands from there. Tests: `pnpm test`. Type/lint gate before finishing: `pnpm build` (tsc + vite) and `pnpm lint`.

---

## File Structure

- **Modify:** `apps/web/src/routes/Approvals.tsx` — the entire feature lives here (tabs, list, rows, action state machine, SSE registration), mirroring how `Inbox.tsx` keeps its sub-components local.
- **Create:** `apps/web/src/routes/__tests__/Approvals.test.tsx` — route tests, mirroring `Inbox.test.tsx` (same `MockEventSource` harness).
- **No changes** to `router.tsx`, `endpoints.ts`, `types.ts`, or any backend file.

Reused helpers (import, don't recreate): `PageHeader`, `EmptyState`, `ErrorState`, `QueryBoundary`, `loadError`, `formatRelativeTime`, `cn`, `useApiQuery`, `useSseInvalidation`, `ApiError`.

---

## Task 1: Tabbed read-only queue (Pending / Approved / Rejected) + live refetch

Builds the page shell: three status tabs, a server-side list fetch per tab, loading/error/empty states, read-only rows, header crumb, and SSE registration. No action buttons yet.

**Files:**
- Modify: `apps/web/src/routes/Approvals.tsx`
- Test: `apps/web/src/routes/__tests__/Approvals.test.tsx` (create)

- [ ] **Step 1: Write the failing tests**

Create `apps/web/src/routes/__tests__/Approvals.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { SseProvider } from '../../lib/events'
import { Approvals } from '../Approvals'
import { listApprovalRequests, resolveAgentSessionApproval } from '../../lib/api'
import type { ApprovalRequest } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockList = vi.mocked(listApprovalRequests)
const mockResolve = vi.mocked(resolveAgentSessionApproval)

// --- MockEventSource (mirrors Inbox.test.tsx) -------------------------------
class MockEventSource {
  static instances: MockEventSource[] = []
  readonly url: string
  readyState: 0 | 1 | 2 = 0
  onopen: (() => void) | null = null
  onerror: ((e: Event) => void) | null = null
  private listeners: Record<string, Set<EventListener>> = {}
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  addEventListener(type: string, listener: EventListener) {
    if (!this.listeners[type]) this.listeners[type] = new Set()
    this.listeners[type].add(listener)
  }
  removeEventListener(type: string, listener: EventListener) {
    this.listeners[type]?.delete(listener)
  }
  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }
  simulateEvent(type: string, data: unknown) {
    const e = Object.assign(new Event(type), { data: JSON.stringify(data) }) as MessageEvent
    this.listeners[type]?.forEach((l) => l(e))
  }
  close() {
    this.readyState = 2
  }
}

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
  cleanup()
})

function renderPage() {
  return render(
    <SseProvider>
      <MemoryRouter initialEntries={['/approvals']}>
        <Approvals />
      </MemoryRouter>
    </SseProvider>,
  )
}

function ar(over: Partial<ApprovalRequest>): ApprovalRequest {
  return {
    id: 'ar1',
    devcontainer_id: 'dc1',
    agent_session_id: 'as1',
    status: 'pending',
    requested_action: 'rm -rf build/',
    created_at: new Date().toISOString(),
    decided_at: null,
    ...over,
  }
}

describe('Approvals states', () => {
  it('shows the spinner while loading', () => {
    mockList.mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('shows the error state when the fetch rejects', async () => {
    mockList.mockRejectedValue(new Error('down'))
    renderPage()
    await waitFor(() => expect(screen.getByText("Couldn't load approvals")).toBeTruthy())
  })

  it('shows the pending empty state when there are no pending requests', async () => {
    mockList.mockResolvedValue({ items: [] })
    renderPage()
    await waitFor(() => expect(screen.getByText('No pending approvals')).toBeTruthy())
  })
})

describe('Approvals tabs', () => {
  it('defaults to the Pending tab and fetches pending requests', async () => {
    mockList.mockResolvedValue({ items: [ar({ id: 'ar1' })] })
    renderPage()
    await screen.findByText('rm -rf build/')
    expect(mockList).toHaveBeenCalledWith({ status: 'pending' })
  })

  it('switching to Approved fetches approved requests', async () => {
    mockList.mockResolvedValue({ items: [] })
    renderPage()
    await screen.findByText('No pending approvals')

    await userEvent.click(screen.getByRole('button', { name: 'Approved' }))
    await waitFor(() => expect(mockList).toHaveBeenCalledWith({ status: 'approved' }))
  })

  it('switching to Rejected fetches rejected requests', async () => {
    mockList.mockResolvedValue({ items: [] })
    renderPage()
    await screen.findByText('No pending approvals')

    await userEvent.click(screen.getByRole('button', { name: 'Rejected' }))
    await waitFor(() => expect(mockList).toHaveBeenCalledWith({ status: 'rejected' }))
  })
})

describe('Approvals live updates', () => {
  it('refetches the list on an approvals invalidation', async () => {
    mockList
      .mockResolvedValueOnce({ items: [ar({ id: 'ar1' })] })
      .mockResolvedValueOnce({ items: [] })
    renderPage()
    await screen.findByText('rm -rf build/')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'approvals', ids: ['ar1'] })
    })

    await waitFor(() => expect(screen.getByText('No pending approvals')).toBeTruthy())
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm test -- Approvals`
Expected: FAIL — `Approvals.tsx` still exports the placeholder; assertions like "No pending approvals" and the `{ status: 'pending' }` call shape don't exist yet.

- [ ] **Step 3: Replace `Approvals.tsx` with the tabbed read-only queue**

Overwrite `apps/web/src/routes/Approvals.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import {
  listApprovalRequests,
  useApiQuery,
  type ApprovalRequest,
  type ApprovalStatus,
} from '../lib/api'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { formatRelativeTime } from '../lib/time'
import { cn } from '../lib/cn'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <path d="m9 11 3 3L22 4" />
  </svg>
)

const TABS: { status: ApprovalStatus; label: string }[] = [
  { status: 'pending', label: 'Pending' },
  { status: 'approved', label: 'Approved' },
  { status: 'rejected', label: 'Rejected' },
]

const EMPTY: Record<ApprovalStatus, { title: string; helper: string }> = {
  pending: {
    title: 'No pending approvals',
    helper: 'Actions Claude Code asks permission for queue here for your decision.',
  },
  approved: { title: 'No approved requests yet', helper: 'Requests you approve appear here.' },
  rejected: { title: 'No rejected requests', helper: 'Requests you reject appear here.' },
}

function badgeClass(status: ApprovalStatus): string {
  switch (status) {
    case 'pending':
      return 'bg-amber-100 text-amber-800'
    case 'approved':
      return 'bg-green-100 text-ok'
    case 'rejected':
      return 'bg-red-100 text-bad'
  }
}

function Tab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-md px-2.5 py-1 text-xs font-semibold',
        active ? 'bg-accent-bg text-accent' : 'text-text-muted hover:bg-surface-muted',
      )}
    >
      {label}
    </button>
  )
}

function ApprovalRow({ request }: { request: ApprovalRequest }) {
  return (
    <div className="flex items-center gap-3 border-b border-border px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="truncate font-mono text-[12.5px] font-semibold text-text">{request.requested_action}</div>
        <div className="mt-0.5 text-[11px] text-text-muted">
          {request.devcontainer_id} · session {request.agent_session_id.slice(0, 8)} ·{' '}
          {formatRelativeTime(request.created_at)}
        </div>
      </div>
      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', badgeClass(request.status))}>
        {request.status}
      </span>
    </div>
  )
}

export function Approvals() {
  const [status, setStatus] = useState<ApprovalStatus>('pending')
  const { state, refetch } = useApiQuery(() => listApprovalRequests({ status }), [status])
  const { register } = useSseInvalidation()

  useEffect(() => register('approvals', refetch), [register, refetch])
  useEffect(() => register('inbox', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetch), [register, refetch])

  const crumbs = state.kind === 'ready' ? `${state.data.items.length} ${status}` : undefined

  return (
    <>
      <PageHeader title="Approvals" crumbs={crumbs} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex gap-1.5 border-b border-border px-4 py-2.5">
          {TABS.map((t) => (
            <Tab key={t.status} label={t.label} active={status === t.status} onClick={() => setStatus(t.status)} />
          ))}
        </div>
        <div className="flex-1 overflow-auto">
          <QueryBoundary state={state} error={<ErrorState {...loadError('approvals')} />}>
            {(data) =>
              data.items.length === 0 ? (
                <EmptyState icon={icon} title={EMPTY[status].title} helper={EMPTY[status].helper} />
              ) : (
                <div>
                  {data.items.map((r) => (
                    <ApprovalRow key={r.id} request={r} />
                  ))}
                </div>
              )
            }
          </QueryBoundary>
        </div>
      </div>
    </>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- Approvals`
Expected: PASS — all Task 1 tests green.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/Approvals.tsx apps/web/src/routes/__tests__/Approvals.test.tsx
git commit -m "VIB-48 Approvals: tabbed read-only queue with live refetch"
```

---

## Task 2: Inline Approve / Reject actions (idle → in-flight → awaiting)

Adds Approve/Reject controls to pending rows. Clicking calls `resolveAgentSessionApproval`; controls disable during the request; on `202` the row shows a "Submitted · awaiting runtime" state and does **not** flip status optimistically.

**Files:**
- Modify: `apps/web/src/routes/Approvals.tsx`
- Modify: `apps/web/src/routes/__tests__/Approvals.test.tsx`

- [ ] **Step 1: Write the failing tests**

Append to the test file (inside the top-level `describe` block list — add a new `describe`):

```tsx
describe('Approvals actions', () => {
  it('approve calls the resolution endpoint with the right ids and resolution', async () => {
    mockList.mockResolvedValue({ items: [ar({ id: 'ar1', devcontainer_id: 'dc9', agent_session_id: 'sess7' })] })
    mockResolve.mockReturnValue(new Promise(() => {})) // stay in flight
    renderPage()
    await screen.findByText('rm -rf build/')

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(mockResolve).toHaveBeenCalledWith('dc9', 'sess7', {
      approval_request_id: 'ar1',
      resolution: 'approved',
    })
  })

  it('reject calls the resolution endpoint with resolution rejected', async () => {
    mockList.mockResolvedValue({ items: [ar({ id: 'ar1' })] })
    mockResolve.mockReturnValue(new Promise(() => {}))
    renderPage()
    await screen.findByText('rm -rf build/')

    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    expect(mockResolve).toHaveBeenCalledWith('dc1', 'as1', {
      approval_request_id: 'ar1',
      resolution: 'rejected',
    })
  })

  it('disables both controls while a request is in flight', async () => {
    mockList.mockResolvedValue({ items: [ar({ id: 'ar1' })] })
    mockResolve.mockReturnValue(new Promise(() => {}))
    renderPage()
    await screen.findByText('rm -rf build/')

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(screen.getByRole('button', { name: /Approving/ })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Reject' })).toHaveProperty('disabled', true)
  })

  it('shows the awaiting state after a 202 without flipping the status', async () => {
    const session = {
      id: 'as1',
      devcontainer_id: 'dc1',
      status: 'waiting_for_approval' as const,
      started_at: null,
      ended_at: null,
      last_event_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    mockList.mockResolvedValue({ items: [ar({ id: 'ar1' })] })
    mockResolve.mockResolvedValue(session)
    renderPage()
    await screen.findByText('rm -rf build/')

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.getByText(/awaiting runtime/i)).toBeTruthy())
    // status badge still reads pending; no Approve/Reject controls remain
    expect(screen.getByText('pending')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm test -- Approvals`
Expected: FAIL — no "Approve"/"Reject" buttons exist yet.

- [ ] **Step 3: Add the action state machine to `Approvals.tsx`**

Add the new imports (extend the existing `../lib/api` import and add `ApiError`):

```tsx
import {
  listApprovalRequests,
  resolveAgentSessionApproval,
  ApiError,
  useApiQuery,
  type ApprovalRequest,
  type ApprovalResolution,
  type ApprovalStatus,
} from '../lib/api'
```

Add an action-button helper and the `ActionState` type above `ApprovalRow`:

```tsx
type ActionState =
  | { kind: 'idle' }
  | { kind: 'submitting'; resolution: ApprovalResolution }
  | { kind: 'awaiting' }

function ActionButton({
  label,
  onClick,
  disabled,
  variant,
}: {
  label: string
  onClick: () => void
  disabled: boolean
  variant: 'approve' | 'reject'
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-md px-3 py-1 text-[12px] font-semibold disabled:opacity-40',
        variant === 'approve' ? 'bg-ok text-white' : 'border border-bad text-bad',
      )}
    >
      {label}
    </button>
  )
}
```

Replace `ApprovalRow` with a version that renders actions for pending rows and owns the action state:

```tsx
function ApprovalRow({ request }: { request: ApprovalRequest }) {
  const [action, setAction] = useState<ActionState>({ kind: 'idle' })

  async function resolve(resolution: ApprovalResolution) {
    setAction({ kind: 'submitting', resolution })
    await resolveAgentSessionApproval(request.devcontainer_id, request.agent_session_id, {
      approval_request_id: request.id,
      resolution,
    })
    setAction({ kind: 'awaiting' })
  }

  const submitting = action.kind === 'submitting'
  const showActions = request.status === 'pending' && action.kind !== 'awaiting'

  return (
    <div className="flex items-center gap-3 border-b border-border px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="truncate font-mono text-[12.5px] font-semibold text-text">{request.requested_action}</div>
        <div className="mt-0.5 text-[11px] text-text-muted">
          {request.devcontainer_id} · session {request.agent_session_id.slice(0, 8)} ·{' '}
          {formatRelativeTime(request.created_at)}
          {action.kind === 'awaiting' && <span className="text-accent"> · submitted · awaiting runtime</span>}
        </div>
      </div>
      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', badgeClass(request.status))}>
        {request.status}
      </span>
      {showActions && (
        <div className="flex shrink-0 gap-2">
          <ActionButton
            label={action.kind === 'submitting' && action.resolution === 'approved' ? 'Approving…' : 'Approve'}
            onClick={() => resolve('approved')}
            disabled={submitting}
            variant="approve"
          />
          <ActionButton
            label={action.kind === 'submitting' && action.resolution === 'rejected' ? 'Rejecting…' : 'Reject'}
            onClick={() => resolve('rejected')}
            disabled={submitting}
            variant="reject"
          />
        </div>
      )}
    </div>
  )
}
```

> Note: `ApiError` is imported now because Task 3 uses it. It is unused until then — if `pnpm lint` flags it between tasks, add it in Task 3 instead. (Task 3 is committed together in normal flow, so this is a non-issue when tasks run in sequence.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- Approvals`
Expected: PASS — Task 1 + Task 2 tests green.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/Approvals.tsx apps/web/src/routes/__tests__/Approvals.test.tsx
git commit -m "VIB-48 Approvals: inline approve/reject with awaiting state"
```

---

## Task 3: Error handling — stale (409) and generic retry

A stale resolution (`APPROVAL_REQUEST_NOT_PENDING`, 409) shows an inline "already resolved" message with controls gone. Any other failure shows an inline retry message and re-enables the controls.

**Files:**
- Modify: `apps/web/src/routes/Approvals.tsx`
- Modify: `apps/web/src/routes/__tests__/Approvals.test.tsx`

- [ ] **Step 1: Write the failing tests**

Add a new `describe` block to the test file. (`ApiError` is already imported at the top of `Inbox.test.tsx`'s pattern — add it to this file's `../../lib/api` import: `import { listApprovalRequests, resolveAgentSessionApproval, ApiError } from '../../lib/api'`.)

```tsx
describe('Approvals action errors', () => {
  it('shows the stale error and removes controls on a 409 not-pending', async () => {
    mockList.mockResolvedValue({ items: [ar({ id: 'ar1' })] })
    mockResolve.mockRejectedValue(
      new ApiError(409, 'APPROVAL_REQUEST_NOT_PENDING', 'already handled'),
    )
    renderPage()
    await screen.findByText('rm -rf build/')

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.getByText(/already resolved elsewhere/i)).toBeTruthy())
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
  })

  it('shows a retry error and re-enables controls on a non-stale failure', async () => {
    mockList.mockResolvedValue({ items: [ar({ id: 'ar1' })] })
    mockResolve.mockRejectedValue(new ApiError(503, 'RUNTIME_UNAVAILABLE', 'no runtime'))
    renderPage()
    await screen.findByText('rm -rf build/')

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.getByText(/couldn't submit/i)).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Reject' })).toHaveProperty('disabled', false)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm test -- Approvals`
Expected: FAIL — no error branches yet; the rejected promise currently goes unhandled.

- [ ] **Step 3: Extend the action state machine with error states**

In `Approvals.tsx`, extend `ActionState`:

```tsx
type ActionState =
  | { kind: 'idle' }
  | { kind: 'submitting'; resolution: ApprovalResolution }
  | { kind: 'awaiting' }
  | { kind: 'stale' }
  | { kind: 'error'; message: string }
```

Replace the `resolve` function and the derived flags inside `ApprovalRow` with the error-aware version:

```tsx
  async function resolve(resolution: ApprovalResolution) {
    setAction({ kind: 'submitting', resolution })
    try {
      await resolveAgentSessionApproval(request.devcontainer_id, request.agent_session_id, {
        approval_request_id: request.id,
        resolution,
      })
      setAction({ kind: 'awaiting' })
    } catch (err) {
      if (err instanceof ApiError && err.code === 'APPROVAL_REQUEST_NOT_PENDING') {
        setAction({ kind: 'stale' })
      } else {
        setAction({ kind: 'error', message: "Couldn't submit — try again." })
      }
    }
  }

  const submitting = action.kind === 'submitting'
  const showActions =
    request.status === 'pending' && action.kind !== 'awaiting' && action.kind !== 'stale'
```

Add the inline message under the meta line — replace the meta `<div>` block's trailing `awaiting` span with both messages:

```tsx
        <div className="mt-0.5 text-[11px] text-text-muted">
          {request.devcontainer_id} · session {request.agent_session_id.slice(0, 8)} ·{' '}
          {formatRelativeTime(request.created_at)}
          {action.kind === 'awaiting' && <span className="text-accent"> · submitted · awaiting runtime</span>}
        </div>
        {action.kind === 'stale' && (
          <div className="mt-1 text-[11px] text-bad">Already resolved elsewhere — no longer pending.</div>
        )}
        {action.kind === 'error' && <div className="mt-1 text-[11px] text-bad">{action.message}</div>}
```

(The stale/error lines live inside the `min-w-0 flex-1` container, just after the meta `<div>`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm test -- Approvals`
Expected: PASS — all Approvals tests green.

- [ ] **Step 5: Type-check, lint, and full test sweep**

Run: `pnpm build && pnpm lint && pnpm test`
Expected: tsc + vite build succeed, no lint errors, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/routes/Approvals.tsx apps/web/src/routes/__tests__/Approvals.test.tsx
git commit -m "VIB-48 Approvals: stale and retry action error handling"
```

---

## Acceptance criteria coverage

- *Page defaults to pending* → Task 1 (default `status='pending'`, test "defaults to the Pending tab").
- *Inspect approved/rejected history* → Task 1 (Approved/Rejected tab tests).
- *Approve/reject via session-scoped endpoint* → Task 2 (resolve call-shape tests).
- *Controls disable in-flight; accepted/pending after 202* → Task 2 (in-flight disable + awaiting-after-202 tests).
- *Stale errors shown clearly* → Task 3 (stale 409 test).
- *Route registers `approvals`, `inbox`, `agent_sessions` scopes* → Task 1 (`useEffect register(...)` + invalidation refetch test).
- *Statuses update after SSE invalidation without refresh* → Task 1 (invalidation refetch test); pending rows leave the list on refetch.
- *Route tests cover pending filter, history, approve, reject, in-flight, success, stale-error, invalidation* → Tasks 1–3 test suites.

## Notes for the implementer

- Tab switching changes the `useApiQuery` dep, which intentionally drops to the loading spinner (per `useApiQuery` semantics) — this is expected, not a bug.
- Row action state is per-row local `useState`; an SSE refetch replaces the list items, so a resolved pending row naturally disappears from the Pending tab. Do not try to persist action state across refetches.
- Do not add a devcontainer filter, a detail panel, or toasts — explicitly out of scope.
