import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SseProvider } from '../../lib/events'
import { RailBackend } from '../RailBackend'
import { fetchHealth, fetchConfig } from '../../lib/api'

vi.mock('../../lib/api/endpoints')
const mockHealth = vi.mocked(fetchHealth)
const mockConfig = vi.mocked(fetchConfig)

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

  it('shows Unreachable when health/config fail', async () => {
    mockHealth.mockRejectedValue(new Error('down'))
    renderComponent()
    await waitFor(() => expect(screen.getByText('Unreachable')).toBeTruthy())
  })

  it('shows service name when connected', async () => {
    renderComponent()
    await waitFor(() => expect(screen.getByText('service: vibing')).toBeTruthy())
  })
})
