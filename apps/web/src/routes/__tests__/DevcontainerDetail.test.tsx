import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { SseProvider } from '../../lib/events'
import { DevcontainerDetail } from '../DevcontainerDetail'
import { fetchDevcontainer, fetchAgentSessions, startAgentSession, stopAgentSession } from '../../lib/api/endpoints'
import { ApiError } from '../../lib/api'
import type { AgentSession, DevcontainerView } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockFetch = vi.mocked(fetchDevcontainer)
const mockFetchSessions = vi.mocked(fetchAgentSessions)
const mockStart = vi.mocked(startAgentSession)
const mockStop = vi.mocked(stopAgentSession)

// ---------------------------------------------------------------------------
// MockEventSource
// ---------------------------------------------------------------------------

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

  simulateError() {
    this.readyState = 0
    this.onerror?.(new Event('error'))
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

function renderPage(id: string) {
  return render(
    <SseProvider>
      <MemoryRouter initialEntries={[`/devcontainers/${id}`]}>
        <Routes>
          <Route path="/devcontainers/:id" element={<DevcontainerDetail />} />
        </Routes>
      </MemoryRouter>
    </SseProvider>,
  )
}

const sample: DevcontainerView = {
  id: 'dc1',
  name: 'my-project',
  local_path: '/home/me/my-project',
  status: 'stopped',
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-16T12:30:00Z',
  runtime: { worker_connected: true, agent_connected: true },
}

const sampleSession: AgentSession = {
  id: 'sess-0001-0000-0000-000000000001',
  devcontainer_id: 'dc1',
  status: 'running',
  started_at: '2024-01-16T10:00:00Z',
  ended_at: null,
  last_event_at: null,
  created_at: '2024-01-16T10:00:00Z',
  updated_at: '2024-01-16T10:00:00Z',
}

describe('DevcontainerDetail', () => {
  it('shows loading spinner while fetching', () => {
    mockFetch.mockReturnValue(new Promise(() => {}))
    mockFetchSessions.mockReturnValue(new Promise(() => {}))
    renderPage('dc1')
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('fetches the devcontainer by id and renders details when ready', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await waitFor(() => expect(mockFetch).toHaveBeenCalledWith('dc1'))
    expect(await screen.findByText('my-project')).toBeTruthy()
    expect(screen.getByText('/home/me/my-project')).toBeTruthy()
    expect(screen.getByText('stopped')).toBeTruthy()
    expect(screen.getByText('2024-01-15T10:00:00Z')).toBeTruthy()
    expect(screen.getByText('2024-01-16T12:30:00Z')).toBeTruthy()
  })

  it('shows generic error state when fetch fails', async () => {
    mockFetch.mockRejectedValue(new Error('down'))
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await waitFor(() => expect(screen.getByText("Couldn't load devcontainer")).toBeTruthy())
  })

  it('shows not-found state when backend returns 404 DEVCONTAINER_NOT_FOUND', async () => {
    mockFetch.mockRejectedValue(new ApiError(404, 'DEVCONTAINER_NOT_FOUND', 'Not found'))
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await waitFor(() => expect(screen.getByText('Devcontainer not found')).toBeTruthy())
    expect(screen.getByText("This devcontainer doesn't exist or has been deleted.")).toBeTruthy()
  })

  it('renders agent sessions section with sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    expect(screen.getByText('running')).toBeTruthy()
    expect(screen.getByText('sess-000')).toBeTruthy()
  })

  it('renders empty state for agent sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    expect(screen.getByText('No agent sessions')).toBeTruthy()
  })
})

describe('SessionControls — guard / disabled states', () => {
  it('AC4: Start disabled and helper text shown when agent_connected is false', async () => {
    const dc = { ...sample, runtime: { worker_connected: false, agent_connected: false } }
    mockFetch.mockResolvedValue(dc)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Start Agent Session')
    const startBtn = screen.getByRole('button', { name: 'Start' }) as HTMLButtonElement
    expect(startBtn.disabled).toBe(true)
    expect(screen.getByText('Agent not connected')).toBeTruthy()
  })

  it('AC3: Start disabled and helper text shown when active session exists', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] }) // status: running
    renderPage('dc1')
    await screen.findByText('Start Agent Session')
    const startBtn = screen.getByRole('button', { name: 'Start' }) as HTMLButtonElement
    expect(startBtn.disabled).toBe(true)
    expect(screen.getByText('A session is already active')).toBeTruthy()
  })

  it('AC1: Start enabled when agent connected and no active session', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Start Agent Session')
    // Start button is disabled until prompt is filled
    const textarea = screen.getByPlaceholderText('Enter a prompt…')
    fireEvent.change(textarea, { target: { value: 'do something' } })
    const startBtn = screen.getByRole('button', { name: 'Start' }) as HTMLButtonElement
    expect(startBtn.disabled).toBe(false)
  })

  it('AC2: Stop button shown when active session exists', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] })
    renderPage('dc1')
    await screen.findByText('Start Agent Session')
    expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy()
  })

  it('AC2: Stop button absent when no active session', async () => {
    mockFetch.mockResolvedValue(sample)
    const completedSession = { ...sampleSession, status: 'completed' as const }
    mockFetchSessions.mockResolvedValue({ items: [completedSession] })
    renderPage('dc1')
    await screen.findByText('Start Agent Session')
    expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull()
  })

  it('AC4: Stop disabled when agent_connected is false', async () => {
    const dc = { ...sample, runtime: { worker_connected: false, agent_connected: false } }
    mockFetch.mockResolvedValue(dc)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] })
    renderPage('dc1')
    await screen.findByText('Start Agent Session')
    const stopBtn = screen.getByRole('button', { name: 'Stop' }) as HTMLButtonElement
    expect(stopBtn.disabled).toBe(true)
  })

  it('AC1: clicking Start calls startAgentSession and refetches sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    mockStart.mockResolvedValue({ ...sampleSession, status: 'starting' })
    renderPage('dc1')
    await screen.findByText('Start Agent Session')
    const textarea = screen.getByPlaceholderText('Enter a prompt…')
    fireEvent.change(textarea, { target: { value: 'do something' } })
    const startBtn = screen.getByRole('button', { name: 'Start' })
    await act(async () => { fireEvent.click(startBtn) })
    expect(mockStart).toHaveBeenCalledWith('dc1', { prompt: 'do something' })
    expect(mockFetchSessions).toHaveBeenCalledTimes(2) // initial + after start
  })

  it('AC2: clicking Stop calls stopAgentSession and refetches sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] })
    mockStop.mockResolvedValue({ ...sampleSession, status: 'stopped' })
    renderPage('dc1')
    await screen.findByText('Start Agent Session')
    const stopBtn = screen.getByRole('button', { name: 'Stop' })
    await act(async () => { fireEvent.click(stopBtn) })
    expect(mockStop).toHaveBeenCalledWith('dc1', 'sess-0001-0000-0000-000000000001')
    expect(mockFetchSessions).toHaveBeenCalledTimes(2) // initial + after stop
  })
})

describe('DevcontainerDetail SSE invalidation', () => {
  it('AC1+AC3+AC4: refetches devcontainer on devcontainers invalidation', async () => {
    mockFetch
      .mockResolvedValueOnce({ ...sample, status: 'stopped' })
      .mockResolvedValueOnce({ ...sample, status: 'running' })
    mockFetchSessions.mockResolvedValue({ items: [] })

    renderPage('dc1')
    await screen.findByText('stopped')

    const callsBefore = mockFetch.mock.calls.length

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'devcontainers', ids: ['dc1'] })
    })

    await waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThan(callsBefore))
    await waitFor(() => expect(screen.getByText('running')).toBeTruthy())
  })

  it('no flash: keeps the detail visible during an invalidation refetch', async () => {
    const second = new Promise<DevcontainerView>(() => {}) // never settles: hold the in-flight window
    mockFetch.mockResolvedValueOnce({ ...sample, status: 'stopped' }).mockReturnValueOnce(second)
    mockFetchSessions.mockResolvedValue({ items: [] })

    renderPage('dc1')
    await screen.findByText('stopped')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'devcontainers', ids: [] })
    })

    await waitFor(() => expect(mockFetch.mock.calls.length).toBe(2))
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.getByText('stopped')).toBeTruthy()
  })

  it('AC2+AC3+AC4: refetches and updates agent session status on agent_sessions invalidation', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions
      .mockResolvedValueOnce({ items: [{ ...sampleSession, status: 'running' }] })
      .mockResolvedValueOnce({ items: [{ ...sampleSession, status: 'completed' }] })

    renderPage('dc1')
    await screen.findByText('running')

    const callsBefore = mockFetchSessions.mock.calls.length

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'agent_sessions', ids: [] })
    })

    await waitFor(() => expect(mockFetchSessions.mock.calls.length).toBeGreaterThan(callsBefore))
    await waitFor(() => expect(screen.getByText('completed')).toBeTruthy())
  })

  it('AC3: badge leaves waiting_for_approval after agent_sessions invalidation', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions
      .mockResolvedValueOnce({ items: [{ ...sampleSession, status: 'waiting_for_approval' }] })
      .mockResolvedValueOnce({ items: [{ ...sampleSession, status: 'running' }] })

    renderPage('dc1')
    await screen.findByText('waiting_for_approval')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'agent_sessions', ids: ['sess-0001-0000-0000-000000000001'] })
    })

    await waitFor(() => expect(screen.getByText('running')).toBeTruthy())
    expect(screen.queryByText('waiting_for_approval')).toBeNull()
  })

  it('AC: single agent_sessions invalidation triggers exactly one refetch', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] })

    renderPage('dc1')
    await screen.findByText('running')

    const callsBefore = mockFetchSessions.mock.calls.length

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'agent_sessions', ids: [] })
    })

    await waitFor(() => expect(mockFetchSessions.mock.calls.length).toBe(callsBefore + 1))
  })
})
