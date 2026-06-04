import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { SseProvider } from '../../lib/events'
import { Approvals } from '../Approvals'
import { listApprovalRequests, resolveAgentSessionApproval, ApiError } from '../../lib/api'
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

  it('refetches the list on an agent_sessions invalidation', async () => {
    mockList
      .mockResolvedValueOnce({ items: [ar({ id: 'ar1' })] })
      .mockResolvedValueOnce({ items: [] })
    renderPage()
    await screen.findByText('rm -rf build/')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'agent_sessions', ids: ['ar1'] })
    })

    await waitFor(() => expect(screen.getByText('No pending approvals')).toBeTruthy())
  })
})

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
    mockList.mockResolvedValue({ items: [ar({ id: 'ar1', devcontainer_id: 'dc8', agent_session_id: 'sess8' })] })
    mockResolve.mockReturnValue(new Promise(() => {}))
    renderPage()
    await screen.findByText('rm -rf build/')

    await userEvent.click(screen.getByRole('button', { name: 'Reject' }))
    expect(mockResolve).toHaveBeenCalledWith('dc8', 'sess8', {
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
    expect(screen.getByText('pending')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull()
  })
})

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
