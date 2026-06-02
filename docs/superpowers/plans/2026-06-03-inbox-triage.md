# Inbox Triage List & Detail Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder Inbox page with a triage workflow: a Needs Attention / All list, a selectable detail side panel backed by `?selected=<id>`, and live status updates via SSE.

**Architecture:** Single `/inbox` route, persistent split-pane (list left, detail right). One unfiltered `listInboxEvents()` query feeds two client-derived views (pure helpers). Selection lives in the URL query param. The list query and the open detail each subscribe to the `inbox`, `agent_sessions`, and `approvals` SSE scopes and refetch on invalidation. Read-only — actions (VIB-50) and toasts (VIB-52) are separate tickets.

**Tech Stack:** React 19, react-router 7 (`useSearchParams`), TypeScript, Tailwind, Vitest + Testing Library. Spec: `docs/superpowers/specs/2026-06-03-inbox-triage-design.md`.

---

## File Structure

- **Create** `apps/web/src/lib/time.ts` — `formatRelativeTime` (extracted from `Devcontainers.tsx`).
- **Create** `apps/web/src/lib/__tests__/time.test.ts` — unit tests for the helper.
- **Create** `apps/web/src/routes/inboxViews.ts` — pure view derivations (`needsAttentionEvents`, `allEvents`).
- **Create** `apps/web/src/routes/__tests__/inboxViews.test.ts` — unit tests for the helpers.
- **Rewrite** `apps/web/src/routes/Inbox.tsx` — the full triage route (list, tabs, selection, detail panel, SSE).
- **Create** `apps/web/src/routes/__tests__/Inbox.test.tsx` — route tests for all AC states.
- **Modify** `apps/web/src/routes/Devcontainers.tsx` — import `formatRelativeTime` from `lib/time` instead of its local copy.

Run all web commands from `apps/web/`.

---

## Task 1: Extract `formatRelativeTime` into a shared util

**Files:**
- Create: `apps/web/src/lib/time.ts`
- Test: `apps/web/src/lib/__tests__/time.test.ts`
- Modify: `apps/web/src/routes/Devcontainers.tsx` (remove local copy, import from `lib/time`)

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/lib/__tests__/time.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { formatRelativeTime } from '../time'

describe('formatRelativeTime', () => {
  it('formats a moment ago as seconds', () => {
    const iso = new Date(Date.now() - 5_000).toISOString()
    expect(formatRelativeTime(iso)).toContain('second')
  })

  it('formats minutes in the past', () => {
    const iso = new Date(Date.now() - 5 * 60_000).toISOString()
    expect(formatRelativeTime(iso)).toContain('minute')
  })

  it('formats hours in the past', () => {
    const iso = new Date(Date.now() - 3 * 60 * 60_000).toISOString()
    expect(formatRelativeTime(iso)).toContain('hour')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- time`
Expected: FAIL — `Cannot find module '../time'`.

- [ ] **Step 3: Create the util**

Create `apps/web/src/lib/time.ts`:

```ts
const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 60 * 60 * 24 * 365],
  ['month', 60 * 60 * 24 * 30],
  ['day', 60 * 60 * 24],
  ['hour', 60 * 60],
  ['minute', 60],
  ['second', 1],
]

const relativeTimeFormat = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

export function formatRelativeTime(iso: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000)
  const abs = Math.abs(seconds)
  for (const [unit, secondsPerUnit] of RELATIVE_UNITS) {
    if (abs >= secondsPerUnit || unit === 'second') {
      return relativeTimeFormat.format(Math.round(seconds / secondsPerUnit), unit)
    }
  }
  return relativeTimeFormat.format(0, 'second')
}
```

- [ ] **Step 4: Point `Devcontainers.tsx` at the shared util**

In `apps/web/src/routes/Devcontainers.tsx`, add to the imports near the top (after the `import { cn } from '../lib/cn'` line):

```ts
import { formatRelativeTime } from '../lib/time'
```

Then delete the now-duplicated block from `Devcontainers.tsx` (the `RELATIVE_UNITS` const, the `relativeTimeFormat` const, and the local `formatRelativeTime` function — currently lines 78–98). Leave `countLabel` and everything else intact.

- [ ] **Step 5: Run tests + typecheck to verify**

Run: `pnpm test -- time Devcontainers && pnpm typecheck`
Expected: PASS — the new `time` tests pass and the existing `Devcontainers` tests still pass (they exercise relative time via the rendered rows), no type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/time.ts apps/web/src/lib/__tests__/time.test.ts apps/web/src/routes/Devcontainers.tsx
git commit -m "VIB-47 extract formatRelativeTime into lib/time"
```

---

## Task 2: Pure view helpers (Needs Attention / All)

**Files:**
- Create: `apps/web/src/routes/inboxViews.ts`
- Test: `apps/web/src/routes/__tests__/inboxViews.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/routes/__tests__/inboxViews.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { needsAttentionEvents, allEvents } from '../inboxViews'
import type { InboxEvent } from '../../lib/api'

function ev(over: Partial<InboxEvent>): InboxEvent {
  return {
    id: 'x',
    devcontainer_id: 'dc',
    agent_session_id: 'as',
    approval_request_id: null,
    event_type: 'question',
    status: 'unread',
    created_at: '2026-06-03T00:00:00Z',
    updated_at: '2026-06-03T00:00:00Z',
    ...over,
  }
}

describe('needsAttentionEvents', () => {
  it('excludes completions and resolved events', () => {
    const events = [
      ev({ id: 'q', event_type: 'question' }),
      ev({ id: 'done', event_type: 'completion' }),
      ev({ id: 'resolved-q', event_type: 'question', status: 'resolved' }),
    ]
    expect(needsAttentionEvents(events).map((e) => e.id)).toEqual(['q'])
  })

  it('orders blocking items (question, approval_request) before failures', () => {
    const events = [
      ev({ id: 'f', event_type: 'failure' }),
      ev({ id: 'a', event_type: 'approval_request' }),
      ev({ id: 'q', event_type: 'question' }),
    ]
    const ids = needsAttentionEvents(events).map((e) => e.id)
    expect(ids.indexOf('q')).toBeLessThan(ids.indexOf('f'))
    expect(ids.indexOf('a')).toBeLessThan(ids.indexOf('f'))
  })

  it('orders newest first within a group', () => {
    const events = [
      ev({ id: 'old', event_type: 'question', created_at: '2026-06-01T00:00:00Z' }),
      ev({ id: 'new', event_type: 'question', created_at: '2026-06-03T00:00:00Z' }),
    ]
    expect(needsAttentionEvents(events).map((e) => e.id)).toEqual(['new', 'old'])
  })
})

describe('allEvents', () => {
  it('includes completions and resolved events, newest first', () => {
    const events = [
      ev({ id: 'old', event_type: 'completion', created_at: '2026-06-01T00:00:00Z' }),
      ev({ id: 'new', event_type: 'question', status: 'resolved', created_at: '2026-06-03T00:00:00Z' }),
    ]
    expect(allEvents(events).map((e) => e.id)).toEqual(['new', 'old'])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- inboxViews`
Expected: FAIL — `Cannot find module '../inboxViews'`.

- [ ] **Step 3: Implement the helpers**

Create `apps/web/src/routes/inboxViews.ts`:

```ts
import type { InboxEvent } from '../lib/api'

const BLOCKING = new Set<InboxEvent['event_type']>(['question', 'approval_request'])

function byCreatedDesc(a: InboxEvent, b: InboxEvent): number {
  return b.created_at.localeCompare(a.created_at)
}

export function needsAttentionEvents(events: InboxEvent[]): InboxEvent[] {
  const open = events.filter((e) => e.event_type !== 'completion' && e.status !== 'resolved')
  const blocking = open.filter((e) => BLOCKING.has(e.event_type)).sort(byCreatedDesc)
  const failures = open.filter((e) => !BLOCKING.has(e.event_type)).sort(byCreatedDesc)
  return [...blocking, ...failures]
}

export function allEvents(events: InboxEvent[]): InboxEvent[] {
  return [...events].sort(byCreatedDesc)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- inboxViews`
Expected: PASS — all five assertions green.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/inboxViews.ts apps/web/src/routes/__tests__/inboxViews.test.ts
git commit -m "VIB-47 add Inbox Needs Attention / All view helpers"
```

---

## Task 3: Inbox route — list, tabs, selection, detail panel, live updates

This task replaces the placeholder `Inbox.tsx` with the full triage route and its test file. Write the test file first (it will fail to compile against the placeholder), then implement.

**Files:**
- Rewrite: `apps/web/src/routes/Inbox.tsx`
- Create: `apps/web/src/routes/__tests__/Inbox.test.tsx`

- [ ] **Step 1: Write the failing route test file**

Create `apps/web/src/routes/__tests__/Inbox.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { SseProvider } from '../../lib/events'
import { Inbox } from '../Inbox'
import { listInboxEvents, fetchInboxEvent } from '../../lib/api'
import type { InboxEvent, InboxEventDetail } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockList = vi.mocked(listInboxEvents)
const mockDetail = vi.mocked(fetchInboxEvent)

// --- MockEventSource (mirrors Devcontainers.test.tsx) -----------------------
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

function renderPage(initialPath = '/inbox') {
  return render(
    <SseProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Inbox />
      </MemoryRouter>
    </SseProvider>,
  )
}

function ev(over: Partial<InboxEvent>): InboxEvent {
  return {
    id: 'ie1',
    devcontainer_id: 'dc1',
    agent_session_id: 'as1',
    approval_request_id: null,
    event_type: 'question',
    status: 'unread',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...over,
  }
}

const sampleDetail: InboxEventDetail = {
  ...ev({ id: 'ie1' }),
  devcontainer: {
    id: 'dc1',
    name: 'api-service',
    local_path: '/home/me/api',
    status: 'running',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  agent_session: {
    id: 'as1session',
    devcontainer_id: 'dc1',
    status: 'running',
    started_at: null,
    ended_at: null,
    last_event_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  approval_request: null,
}

describe('Inbox states', () => {
  it('shows the spinner while loading', () => {
    mockList.mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('shows the error state when the fetch rejects', async () => {
    mockList.mockRejectedValue(new Error('down'))
    renderPage()
    await waitFor(() => expect(screen.getByText("Couldn't load inbox")).toBeTruthy())
  })

  it('shows the needs-attention empty state when nothing needs attention', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'c', event_type: 'completion' })] })
    renderPage()
    await waitFor(() => expect(screen.getByText('Nothing needs attention')).toBeTruthy())
  })
})

describe('Inbox views', () => {
  it('lists needs-attention items with blocking before failures', async () => {
    mockList.mockResolvedValue({
      items: [
        ev({ id: 'f', event_type: 'failure', devcontainer_id: 'cli' }),
        ev({ id: 'q', event_type: 'question' }),
      ],
    })
    renderPage()
    await screen.findByText('Blocking')
    expect(screen.getByText('Failures')).toBeTruthy()
    const labels = screen.getAllByText(/Blocking|Failures/).map((n) => n.textContent)
    expect(labels.indexOf('Blocking')).toBeLessThan(labels.indexOf('Failures'))
  })

  it('hides completions in Needs Attention but shows them under All', async () => {
    mockList.mockResolvedValue({
      items: [ev({ id: 'c', event_type: 'completion' }), ev({ id: 'q', event_type: 'question' })],
    })
    renderPage()
    await screen.findByText('Blocking')
    expect(screen.queryByText('completion')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'All' }))
    await waitFor(() => expect(screen.getByText('completion')).toBeTruthy())
  })
})

describe('Inbox selection + detail', () => {
  it('clicking a row selects it and shows the detail panel', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    renderPage()
    await screen.findByText('Blocking')

    await userEvent.click(screen.getByText('api-service', { selector: 'span' }).closest('button')!)
    await waitFor(() => expect(mockDetail).toHaveBeenCalledWith('ie1'))
  })

  it('renders the detail from the URL on load (survives refresh)', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    renderPage('/inbox?selected=ie1')
    await waitFor(() => expect(mockDetail).toHaveBeenCalledWith('ie1'))
    await waitFor(() => expect(screen.getByText('running')).toBeTruthy())
  })

  it('shows the empty hint when nothing is selected', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    renderPage()
    await waitFor(() => expect(screen.getByText('Select an item')).toBeTruthy())
  })
})

describe('Inbox live updates', () => {
  it('updates a list row status on inbox invalidation', async () => {
    mockList
      .mockResolvedValueOnce({ items: [ev({ id: 'ie1', status: 'unread' })] })
      .mockResolvedValueOnce({ items: [ev({ id: 'ie1', status: 'read' })] })
    renderPage()
    await screen.findByText('unread')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: ['ie1'] })
    })

    await waitFor(() => expect(screen.getByText('read')).toBeTruthy())
  })

  it('updates the open detail status on inbox invalidation', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail
      .mockResolvedValueOnce({ ...sampleDetail, status: 'unread' })
      .mockResolvedValueOnce({ ...sampleDetail, status: 'resolved' })
    renderPage('/inbox?selected=ie1')
    await screen.findByText('unread')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: ['ie1'] })
    })

    await waitFor(() => expect(screen.getByText('resolved')).toBeTruthy())
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm test -- Inbox`
Expected: FAIL — the placeholder `Inbox` renders none of the expected text/roles (e.g. "Blocking", the `All` button, "Select an item").

- [ ] **Step 3: Implement the full Inbox route**

Replace the entire contents of `apps/web/src/routes/Inbox.tsx` with:

```tsx
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import {
  listInboxEvents,
  fetchInboxEvent,
  useApiQuery,
  ApiError,
  type InboxEvent,
  type InboxEventDetail,
  type QueryState,
} from '../lib/api'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { formatRelativeTime } from '../lib/time'
import { cn } from '../lib/cn'
import { needsAttentionEvents, allEvents } from './inboxViews'

const inboxIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
  </svg>
)

type View = 'needs' | 'all'

const TYPE_LABEL: Record<InboxEvent['event_type'], string> = {
  question: 'question',
  approval_request: 'approval request',
  completion: 'completion',
  failure: 'failure',
}

function typeBadgeClass(type: InboxEvent['event_type']): string {
  switch (type) {
    case 'question':
      return 'bg-accent-bg text-accent'
    case 'approval_request':
      return 'bg-amber-100 text-amber-800'
    case 'failure':
      return 'bg-red-100 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function ViewTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
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

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-surface-muted px-4 py-1.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
      {children}
    </div>
  )
}

function InboxRow({
  event,
  selected,
  onSelect,
}: {
  event: InboxEvent
  selected: boolean
  onSelect: (id: string) => void
}) {
  return (
    <button
      onClick={() => onSelect(event.id)}
      className={cn(
        'flex w-full flex-col gap-1 border-b border-border px-4 py-2.5 text-left',
        selected ? 'border-l-[3px] border-l-accent bg-accent-bg/40 pl-[13px]' : 'hover:bg-surface-muted',
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium capitalize', typeBadgeClass(event.event_type))}>
          {TYPE_LABEL[event.event_type]}
        </span>
        <span className="text-[12.5px] font-semibold text-text">{event.devcontainer_id}</span>
      </div>
      <div className="text-[11px] text-text-muted">
        {event.status} · {formatRelativeTime(event.created_at)}
      </div>
    </button>
  )
}

function InboxList({
  events,
  view,
  selectedId,
  onSelect,
}: {
  events: InboxEvent[]
  view: View
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const row = (e: InboxEvent) => (
    <InboxRow key={e.id} event={e} selected={e.id === selectedId} onSelect={onSelect} />
  )

  if (view === 'all') return <div>{events.map(row)}</div>

  const blocking = events.filter((e) => e.event_type === 'question' || e.event_type === 'approval_request')
  const failures = events.filter((e) => e.event_type === 'failure')
  return (
    <div>
      {blocking.length > 0 && (
        <>
          <GroupLabel>Blocking</GroupLabel>
          {blocking.map(row)}
        </>
      )}
      {failures.length > 0 && (
        <>
          <GroupLabel>Failures</GroupLabel>
          {failures.map(row)}
        </>
      )}
    </div>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 border-b border-border px-4 py-3 last:border-b-0">
      <span className="w-32 shrink-0 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">{label}</span>
      <span className="text-[13px] text-text">{children}</span>
    </div>
  )
}

function InboxDetail({ detail, onClose }: { detail: InboxEventDetail; onClose: () => void }) {
  return (
    <div className="px-4 pt-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold capitalize text-text">{TYPE_LABEL[detail.event_type]}</h2>
        <button
          onClick={onClose}
          title="Close"
          className="flex h-7 w-7 items-center justify-center rounded-[5px] text-text-muted hover:bg-surface-muted"
        >
          ✕
        </button>
      </div>
      <div className="rounded-md border border-border">
        <DetailRow label="Status">{detail.status}</DetailRow>
        <DetailRow label="Devcontainer">{detail.devcontainer.name}</DetailRow>
        <DetailRow label="Agent session">
          {detail.agent_session ? `${detail.agent_session.id.slice(0, 8)} · ${detail.agent_session.status}` : '—'}
        </DetailRow>
        <DetailRow label="Approval request">
          {detail.approval_request
            ? `${detail.approval_request.requested_action} · ${detail.approval_request.status}`
            : '—'}
        </DetailRow>
        <DetailRow label="Created">{formatRelativeTime(detail.created_at)}</DetailRow>
      </div>
    </div>
  )
}

function detailErrorElement(state: QueryState<InboxEventDetail>) {
  if (state.kind === 'error' && state.error instanceof ApiError && state.error.code === 'INBOX_EVENT_NOT_FOUND') {
    return <ErrorState title="Inbox event not found" helper="This item doesn't exist or has been removed." />
  }
  return <ErrorState {...loadError('inbox event')} />
}

function InboxDetailPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const { state, refetch } = useApiQuery(() => fetchInboxEvent(id), [id])
  const { register } = useSseInvalidation()

  useEffect(() => register('inbox', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetch), [register, refetch])
  useEffect(() => register('approvals', refetch), [register, refetch])

  return (
    <QueryBoundary state={state} error={detailErrorElement(state)}>
      {(detail) => <InboxDetail detail={detail} onClose={onClose} />}
    </QueryBoundary>
  )
}

export function Inbox() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('selected')
  const [view, setView] = useState<View>('needs')
  const { state, refetch } = useApiQuery(() => listInboxEvents(), [])
  const { register } = useSseInvalidation()

  useEffect(() => register('inbox', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetch), [register, refetch])
  useEffect(() => register('approvals', refetch), [register, refetch])

  function select(id: string) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('selected', id)
        return next
      },
      { replace: false },
    )
  }

  function clearSelection() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('selected')
      return next
    })
  }

  const crumbs = state.kind === 'ready' ? `${needsAttentionEvents(state.data.items).length} need attention` : undefined

  return (
    <>
      <PageHeader title="Inbox" crumbs={crumbs} />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-[340px] shrink-0 flex-col border-r border-border">
          <div className="flex gap-1.5 border-b border-border px-4 py-2.5">
            <ViewTab label="Needs Attention" active={view === 'needs'} onClick={() => setView('needs')} />
            <ViewTab label="All" active={view === 'all'} onClick={() => setView('all')} />
          </div>
          <div className="flex-1 overflow-auto">
            <QueryBoundary state={state} error={<ErrorState {...loadError('inbox')} />}>
              {(data) => {
                const events = view === 'needs' ? needsAttentionEvents(data.items) : allEvents(data.items)
                return events.length === 0 ? (
                  <EmptyState
                    icon={inboxIcon}
                    title={view === 'needs' ? 'Nothing needs attention' : 'Inbox is empty'}
                    helper="Questions, approval requests, failures and completions from your agent sessions appear here."
                  />
                ) : (
                  <InboxList events={events} view={view} selectedId={selectedId} onSelect={select} />
                )
              }}
            </QueryBoundary>
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          {selectedId ? (
            <InboxDetailPanel key={selectedId} id={selectedId} onClose={clearSelection} />
          ) : (
            <EmptyState icon={inboxIcon} title="Select an item" helper="Choose an Inbox event to see its details." />
          )}
        </div>
      </div>
    </>
  )
}
```

Note: `QueryState` is exported from `../lib/api` (via the `useApiQuery` barrel). The `InboxDetailPanel` is keyed by `id` so switching selection remounts it and re-runs its query cleanly.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm test -- Inbox`
Expected: PASS — all `Inbox states`, `Inbox views`, `Inbox selection + detail`, and `Inbox live updates` tests green.

- [ ] **Step 5: Full web verification**

Run: `pnpm test && pnpm lint && pnpm typecheck`
Expected: PASS — whole web suite green, no lint or type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/routes/Inbox.tsx apps/web/src/routes/__tests__/Inbox.test.tsx
git commit -m "VIB-47 build Inbox triage list and detail panel"
```

---

## Task 4: Final verification & ticket update

**Files:** none (verification + Jira).

- [ ] **Step 1: Run the full web suite one more time**

Run (from `apps/web/`): `pnpm test && pnpm lint && pnpm typecheck`
Expected: PASS — all green.

- [ ] **Step 2: Verify against acceptance criteria**

Confirm each VIB-47 AC maps to passing tests / code:
- Defaults to Needs Attention view → `view` initial state `'needs'`; `Inbox views` tests.
- Questions/approvals before failures → `inboxViews` ordering test + `Inbox views` group-order test.
- Completions omitted from Needs Attention, visible in All → `inboxViews` + `Inbox views` toggle test.
- Selecting opens detail backed by detail API → `Inbox selection + detail` click test.
- `/inbox?selected=<id>` survives refresh → `renders the detail from the URL on load` test.
- Registers `inbox`, `agent_sessions`, `approvals` scopes → `useEffect register(...)` in list + detail panel.
- List rows + detail update after SSE without refresh → `Inbox live updates` tests.

- [ ] **Step 3: Move the Jira ticket to In Review with a result comment**

Add a short comment summarizing the result, then transition VIB-47 (id `10234`) to In Review (transition id `31`) using the jira MCP tools (cloudId `70b0455e-11e5-47f8-8c2a-f91ba4065e51`). Comment focus: Inbox triage list + detail panel shipped with Needs Attention/All views, URL-encoded selection, and SSE-driven live updates; all web checks green.

---

## Self-Review notes

- **Spec coverage:** every AC has a task/test (mapped in Task 4 Step 2). The `formatRelativeTime` extraction (spec "Shared util cleanup") is Task 1.
- **Type consistency:** helpers `needsAttentionEvents` / `allEvents` defined in Task 2 are used identically in Task 3; `InboxEvent` / `InboxEventDetail` / `QueryState` come from the existing `lib/api` barrel; `register(scope, refetch)` returns the unregister cleanup consumed by the `useEffect`s.
- **No placeholders:** all code blocks are complete and runnable.
