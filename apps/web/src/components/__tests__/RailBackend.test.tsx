import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SseProvider } from '../../lib/events'
import { RailBackend } from '../RailBackend'
import { fetchHealth, fetchConfig, fetchRuntimeStatus } from '../../lib/api'

vi.mock('../../lib/api/endpoints')
const mockHealth = vi.mocked(fetchHealth)
const mockConfig = vi.mocked(fetchConfig)
const mockRuntime = vi.mocked(fetchRuntimeStatus)

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
  mockHealth.mockResolvedValue({ status: 'ok', service: 'vibing' })
  mockConfig.mockResolvedValue({ app_name: 'vibing', api_v1_prefix: '/api/v1' })
  mockRuntime.mockResolvedValue({ worker_connected: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
  cleanup()
})

function renderComponent() {
  return render(
    <SseProvider>
      <MemoryRouter>
        <RailBackend />
      </MemoryRouter>
    </SseProvider>,
  )
}

describe('RailBackend', () => {
  it('shows Connected when health/config load successfully', async () => {
    renderComponent()
    await waitFor(() => expect(screen.getByText('Connected')).toBeTruthy())
  })

  it('shows Worker disconnected when worker_connected is false', async () => {
    mockRuntime.mockResolvedValue({ worker_connected: false })
    renderComponent()
    await waitFor(() => expect(screen.getByText('Worker disconnected')).toBeTruthy())
  })

  it('shows Worker connected when worker_connected is true', async () => {
    mockRuntime.mockResolvedValue({ worker_connected: true })
    renderComponent()
    await waitFor(() => expect(screen.getByText('Worker connected')).toBeTruthy())
  })

  it('refetches runtime status on runtime SSE invalidation', async () => {
    mockRuntime
      .mockResolvedValueOnce({ worker_connected: false })
      .mockResolvedValueOnce({ worker_connected: true })

    renderComponent()
    await screen.findByText('Worker disconnected')

    const callsBefore = mockRuntime.mock.calls.length

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'runtime', ids: [] })
    })

    await waitFor(() => expect(mockRuntime.mock.calls.length).toBeGreaterThan(callsBefore))
    await waitFor(() => expect(screen.getByText('Worker connected')).toBeTruthy())
  })

  it('uses useApiQuery (SWR): keeps worker status visible during a runtime refetch', async () => {
    const second = new Promise<{ worker_connected: boolean }>(() => {}) // never settles
    mockRuntime
      .mockResolvedValueOnce({ worker_connected: true })
      .mockReturnValueOnce(second)

    renderComponent()
    await screen.findByText('Worker connected')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'runtime', ids: [] })
    })

    await waitFor(() => expect(mockRuntime.mock.calls.length).toBe(2))
    // Still showing old data during refetch — no flash to disconnected
    expect(screen.getByText('Worker connected')).toBeTruthy()
  })
})
