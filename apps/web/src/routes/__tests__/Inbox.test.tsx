import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { SseProvider } from '../../lib/events'
import { Inbox } from '../Inbox'
import { listInboxEvents, fetchInboxEvent, sendAgentSessionUserInput, resolveAgentSessionApproval, markInboxEventRead, resolveInboxEvent, ApiError } from '../../lib/api'
import type { InboxEvent, InboxEventDetail } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockList = vi.mocked(listInboxEvents)
const mockDetail = vi.mocked(fetchInboxEvent)
const mockSend = vi.mocked(sendAgentSessionUserInput)
const mockResolve = vi.mocked(resolveAgentSessionApproval)
const mockRead = vi.mocked(markInboxEventRead)
const mockResolveInbox = vi.mocked(resolveInboxEvent)

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
  // default: auto-read resolves to a read copy; tests can override
  mockRead.mockResolvedValue({ ...sampleDetail, status: 'read' } as InboxEvent)
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
  content: 'Redis or in-memory?',
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
    prompt: null,
    started_at: null,
    ended_at: null,
    last_event_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  approval_request: null,
}

const approvalDetail: InboxEventDetail = {
  ...ev({ id: 'ie2', event_type: 'approval_request', approval_request_id: 'ar1' }),
  content: null,
  devcontainer: sampleDetail.devcontainer,
  agent_session: sampleDetail.agent_session,
  approval_request: {
    id: 'ar1',
    devcontainer_id: 'dc1',
    agent_session_id: 'as1',
    status: 'pending',
    requested_action: 'run: pnpm migrate',
    created_at: new Date().toISOString(),
    decided_at: null,
  },
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

    await userEvent.click(screen.getByText('dc1', { selector: 'span' }).closest('button')!)
    await waitFor(() => expect(mockDetail).toHaveBeenCalledWith('ie1'))
  })

  it('renders the detail from the URL on load (survives refresh)', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    renderPage('/inbox?selected=ie1')
    await waitFor(() => expect(mockDetail).toHaveBeenCalledWith('ie1'))
    await waitFor(() => expect(screen.getByText('Redis or in-memory?')).toBeTruthy())
  })

  it('shows the empty hint when nothing is selected', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    renderPage()
    await waitFor(() => expect(screen.getByText('Select an item')).toBeTruthy())
  })

  it('shows a not-found error for a stale selected id but still renders the list', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockRejectedValue(new ApiError(404, 'INBOX_EVENT_NOT_FOUND', 'gone'))
    renderPage('/inbox?selected=missing')

    await waitFor(() => expect(screen.getByText('Inbox event not found')).toBeTruthy())
    // list still renders its row
    expect(screen.getByText('dc1', { selector: 'span' })).toBeTruthy()
  })

  it('closing the detail panel clears the selection', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    renderPage('/inbox?selected=ie1')

    // detail loaded (question bubble shows in the panel)
    await screen.findByText('Redis or in-memory?')

    await userEvent.click(screen.getByTitle('Close'))
    await waitFor(() => expect(screen.getByText('Select an item')).toBeTruthy())
    expect(screen.queryByText('Redis or in-memory?')).toBeNull()
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

  // AC1: new event projected via SSE updates list rows and needs-attention count
  it('AC1: creation adds a new row and updates the needs-attention count in place', async () => {
    mockList
      .mockResolvedValueOnce({ items: [ev({ id: 'ie1', event_type: 'question' })] })
      .mockResolvedValueOnce({
        items: [
          ev({ id: 'ie1', event_type: 'question' }),
          ev({ id: 'ie2', event_type: 'question', devcontainer_id: 'dc2' }),
        ],
      })
    renderPage()
    // Initial render: 1 item, count says "1 need attention"
    await screen.findByText('1 need attention')
    expect(screen.queryByText('dc2')).toBeNull()

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: [] })
    })

    // After refetch: new row appears and count updates — no manual refresh
    await waitFor(() => expect(screen.getByText('dc2')).toBeTruthy())
    expect(screen.getByText('2 need attention')).toBeTruthy()
  })

  // AC2: stale-while-revalidate — no flash during background refetch
  it('AC2: keeps list visible with no spinner while background refetch is in flight', async () => {
    // second call never settles — holds the in-flight window open
    mockList
      .mockResolvedValueOnce({ items: [ev({ id: 'ie1', event_type: 'question' })] })
      .mockReturnValueOnce(new Promise(() => {}))
    renderPage()
    await screen.findByText('dc1')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: [] })
    })

    // Wait until the second call fired so we are genuinely in-flight
    await waitFor(() => expect(mockList.mock.calls.length).toBe(2))

    // Stale data stays on screen; no page-level loading spinner
    expect(screen.getByText('dc1')).toBeTruthy()
    expect(screen.queryByRole('status')).toBeNull()
  })

  // AC3: detail-panel resolved-state-in-place is covered by the existing test
  // "hides controls and reflects resolved state after an invalidation refetch" in
  // Inbox intervention actions — no redundant test added here.
})

describe('Inbox intervention actions', () => {
  it('answers a question and shows the awaiting note after 202', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    mockSend.mockResolvedValue(sampleDetail.agent_session!)
    renderPage('/inbox?selected=ie1')

    await screen.findByText('Redis or in-memory?')
    await userEvent.type(screen.getByPlaceholderText('Type your answer…'), 'Use Redis')
    await userEvent.click(screen.getByText('Send answer'))

    await waitFor(() => expect(mockSend).toHaveBeenCalledWith('dc1', 'as1', { inbox_event_id: 'ie1', text: 'Use Redis' }))
    await waitFor(() => expect(screen.getByText('✓ Answer sent · awaiting runtime…')).toBeTruthy())
  })

  it('disables the send button while the answer is in flight', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    mockSend.mockReturnValue(new Promise(() => {}))
    renderPage('/inbox?selected=ie1')

    await screen.findByText('Redis or in-memory?')
    await userEvent.type(screen.getByPlaceholderText('Type your answer…'), 'Use Redis')
    await userEvent.click(screen.getByText('Send answer'))
    await waitFor(() => expect((screen.getByText('Sending…') as HTMLButtonElement).disabled).toBe(true))
  })

  it('shows the stale note when the question is no longer actionable', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    mockSend.mockRejectedValue(new ApiError(409, 'INBOX_EVENT_NOT_ACTIONABLE', 'gone'))
    renderPage('/inbox?selected=ie1')

    await screen.findByText('Redis or in-memory?')
    await userEvent.type(screen.getByPlaceholderText('Type your answer…'), 'Use Redis')
    await userEvent.click(screen.getByText('Send answer'))
    await waitFor(() => expect(screen.getByText('This question is no longer awaiting an answer.')).toBeTruthy())
  })

  it('approves an approval request and shows the awaiting note', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request' })] })
    mockDetail.mockResolvedValue(approvalDetail)
    mockResolve.mockResolvedValue(sampleDetail.agent_session!)
    renderPage('/inbox?selected=ie2')

    await screen.findByText('Claude wants to run: pnpm migrate')
    await userEvent.click(screen.getByText('Approve'))
    await waitFor(() => expect(mockResolve).toHaveBeenCalledWith('dc1', 'as1', { approval_request_id: 'ar1', resolution: 'approved' }))
    await waitFor(() => expect(screen.getByText('✓ Submitted · awaiting runtime…')).toBeTruthy())
  })

  it('rejects an approval request', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request' })] })
    mockDetail.mockResolvedValue(approvalDetail)
    mockResolve.mockResolvedValue(sampleDetail.agent_session!)
    renderPage('/inbox?selected=ie2')

    await screen.findByText('Claude wants to run: pnpm migrate')
    await userEvent.click(screen.getByText('Reject'))
    await waitFor(() => expect(mockResolve).toHaveBeenCalledWith('dc1', 'as1', { approval_request_id: 'ar1', resolution: 'rejected' }))
  })

  it('shows the stale note when the approval is no longer pending', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request' })] })
    mockDetail.mockResolvedValue(approvalDetail)
    mockResolve.mockRejectedValue(new ApiError(409, 'APPROVAL_REQUEST_NOT_PENDING', 'gone'))
    renderPage('/inbox?selected=ie2')

    await screen.findByText('Claude wants to run: pnpm migrate')
    await userEvent.click(screen.getByText('Approve'))
    await waitFor(() => expect(screen.getByText('Already resolved elsewhere — no longer pending.')).toBeTruthy())
  })

  it('hides controls and reflects resolved state after an invalidation refetch', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail
      .mockResolvedValueOnce(sampleDetail)
      .mockResolvedValueOnce({ ...sampleDetail, status: 'resolved' })
    renderPage('/inbox?selected=ie1')
    await screen.findByPlaceholderText('Type your answer…')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: ['ie1'] })
    })

    await waitFor(() => expect(screen.queryByPlaceholderText('Type your answer…')).toBeNull())
  })
})

const unreadDetail: InboxEventDetail = {
  id: 'evt1',
  devcontainer_id: 'dc1',
  agent_session_id: null,
  approval_request_id: null,
  event_type: 'question',
  status: 'unread',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  content: 'Pick a name?',
  devcontainer: {
    id: 'dc1',
    name: 'env',
    local_path: '/w',
    status: 'running',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  agent_session: null,
  approval_request: null,
}

// Use status: 'read' to prevent the auto-markRead side-effect from consuming the second mock return
const readApprovalDetail: InboxEventDetail = { ...approvalDetail, status: 'read' }

describe('Inbox approval detail convergence (AC1, AC2, AC4, AC5)', () => {
  it('AC1: approve from detail — controls hide after action + inbox invalidation returns resolved detail', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request', status: 'read' })] })
    mockDetail
      .mockResolvedValueOnce(readApprovalDetail)
      .mockResolvedValueOnce({ ...readApprovalDetail, status: 'resolved' })
    mockResolve.mockResolvedValue(approvalDetail.agent_session!)
    renderPage('/inbox?selected=ie2')
    await screen.findByText('Claude wants to run: pnpm migrate')

    await userEvent.click(screen.getByText('Approve'))
    await waitFor(() => expect(mockResolve).toHaveBeenCalled())

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: ['ie2'] })
    })

    // After SSE-triggered refetch returns resolved detail, approval controls disappear
    await waitFor(() => expect(screen.queryByText('Approve')).toBeNull())
    expect(screen.queryByText('Reject')).toBeNull()
  })

  it('AC2: reject from detail — controls hide after action + approvals invalidation returns resolved detail', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request', status: 'read' })] })
    mockDetail
      .mockResolvedValueOnce(readApprovalDetail)
      .mockResolvedValueOnce({ ...readApprovalDetail, status: 'resolved' })
    mockResolve.mockResolvedValue(approvalDetail.agent_session!)
    renderPage('/inbox?selected=ie2')
    await screen.findByText('Claude wants to run: pnpm migrate')

    await userEvent.click(screen.getByText('Reject'))
    await waitFor(() => expect(mockResolve).toHaveBeenCalled())

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'approvals', ids: ['ar1'] })
    })

    await waitFor(() => expect(screen.queryByText('Reject')).toBeNull())
    expect(screen.queryByText('Approve')).toBeNull()
  })

  it('AC5: no flash in detail — stale approval content visible while refetch is in flight', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request', status: 'read' })] })
    mockDetail
      .mockResolvedValueOnce(readApprovalDetail)
      .mockReturnValueOnce(new Promise(() => {})) // never settles
    renderPage('/inbox?selected=ie2')
    await screen.findByText('Claude wants to run: pnpm migrate')

    const callsBefore = mockDetail.mock.calls.length

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'approvals', ids: ['ar1'] })
    })

    await waitFor(() => expect(mockDetail.mock.calls.length).toBeGreaterThan(callsBefore))

    // Stale content stays on screen; no spinner
    expect(screen.getByText('Claude wants to run: pnpm migrate')).toBeTruthy()
    expect(screen.queryByRole('status')).toBeNull()
  })
})

describe('Inbox completion and failure content rendering', () => {
  const completionDetail: InboxEventDetail = {
    ...ev({ id: 'ie-comp', event_type: 'completion', status: 'read' }),
    content: 'All 42 tests passed.',
    devcontainer: sampleDetail.devcontainer,
    agent_session: sampleDetail.agent_session,
    approval_request: null,
  }

  const failureDetail: InboxEventDetail = {
    ...ev({ id: 'ie-fail', event_type: 'failure', status: 'read' }),
    content: 'Error: ENOENT /app/config.json',
    devcontainer: sampleDetail.devcontainer,
    agent_session: sampleDetail.agent_session,
    approval_request: null,
  }

  const completionNoContent: InboxEventDetail = {
    ...ev({ id: 'ie-comp2', event_type: 'completion', status: 'read' }),
    content: null,
    devcontainer: sampleDetail.devcontainer,
    agent_session: sampleDetail.agent_session,
    approval_request: null,
  }

  it('renders content bubble for completion event with result', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie-comp', event_type: 'completion', status: 'read' })] })
    mockDetail.mockResolvedValue(completionDetail)
    renderPage('/inbox?selected=ie-comp')
    await waitFor(() => expect(screen.getByText('All 42 tests passed.')).toBeTruthy())
    // meta table still present
    expect(screen.getByText('api-service')).toBeTruthy()
  })

  it('renders content bubble for failure event with stderr_tail', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie-fail', event_type: 'failure', status: 'read' })] })
    mockDetail.mockResolvedValue(failureDetail)
    renderPage('/inbox?selected=ie-fail')
    await waitFor(() => expect(screen.getByText('Error: ENOENT /app/config.json')).toBeTruthy())
    expect(screen.getByText('api-service')).toBeTruthy()
  })

  it('omits content bubble when completion has no result', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie-comp2', event_type: 'completion', status: 'read' })] })
    mockDetail.mockResolvedValue(completionNoContent)
    renderPage('/inbox?selected=ie-comp2')
    // meta table visible
    await waitFor(() => expect(screen.getByText('api-service')).toBeTruthy())
    // no content bubble
    expect(screen.queryByText('All 42 tests passed.')).toBeNull()
  })
})

describe('Inbox read/resolve actions', () => {
  it('fires markInboxEventRead when opening an unread event', async () => {
    mockList.mockResolvedValue({ items: [{ ...unreadDetail }] as InboxEvent[] })
    mockDetail.mockResolvedValue(unreadDetail)
    mockRead.mockResolvedValue({ ...unreadDetail, status: 'read' } as InboxEvent)
    renderPage('/inbox?selected=evt1')
    await waitFor(() => expect(mockRead).toHaveBeenCalledWith('evt1'))
    expect(mockRead).toHaveBeenCalledTimes(1)
  })

  it('does not fire markInboxEventRead for a read event', async () => {
    const readDetail = { ...unreadDetail, status: 'read' as const }
    mockList.mockResolvedValue({ items: [readDetail] as InboxEvent[] })
    mockDetail.mockResolvedValue(readDetail)
    renderPage('/inbox?selected=evt1')
    await screen.findByText('Pick a name?')
    expect(mockRead).not.toHaveBeenCalled()
  })

  it('does not fire markInboxEventRead for a resolved event', async () => {
    const resolvedDetail = { ...unreadDetail, status: 'resolved' as const }
    mockList.mockResolvedValue({ items: [resolvedDetail] as InboxEvent[] })
    mockDetail.mockResolvedValue(resolvedDetail)
    renderPage('/inbox?selected=evt1')
    await screen.findByText('Resolved')
    expect(mockRead).not.toHaveBeenCalled()
  })

  it('resolves an event when the resolve button is clicked', async () => {
    mockList.mockResolvedValue({ items: [{ ...unreadDetail }] as InboxEvent[] })
    mockDetail.mockResolvedValue(unreadDetail)
    mockRead.mockResolvedValue({ ...unreadDetail, status: 'read' } as InboxEvent)
    mockResolveInbox.mockResolvedValue({ ...unreadDetail, status: 'resolved' } as InboxEvent)
    renderPage('/inbox?selected=evt1')
    const btn = await screen.findByRole('button', { name: /resolve/i })
    await userEvent.click(btn)
    await waitFor(() => expect(mockResolveInbox).toHaveBeenCalledWith('evt1'))
  })
})
