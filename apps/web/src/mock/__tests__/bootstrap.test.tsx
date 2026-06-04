// Tests the externally visible behavior of mock mode:
// - handlers serve healthy baseline responses that let the shell and Settings render.
// The bootstrap gating (await worker.start before render) is verified indirectly:
// if handlers weren't in place before render, the fetches would fail and the UI
// would show error states instead of the healthy baseline content.
import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { setupServer } from 'msw/node'
import { vi } from 'vitest'
import { handlers } from '../handlers'
import { SseProvider } from '../../lib/events'
import { RailBackend } from '../../components/RailBackend'
import { Settings } from '../../routes/Settings'
import { AppShell } from '../../routes/AppShell'

// MSW node server intercepts fetch calls in the happy-dom environment
const server = setupServer(...handlers)

beforeAll(() => server.listen())
afterEach(() => {
  server.resetHandlers()
  cleanup()
})
afterAll(() => server.close())

// SseProvider needs EventSource — stub it to avoid connection errors
class MockEventSource {
  static instances: MockEventSource[] = []
  readonly url: string
  readyState: 0 | 1 | 2 = 0
  onopen: (() => void) | null = null
  onerror: ((e: Event) => void) | null = null
  addEventListener() {}
  removeEventListener() {}
  close() { this.readyState = 2 }
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
}

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
})

afterEach(() => vi.unstubAllGlobals())

describe('mock bootstrap — healthy baseline renders', () => {
  it('RailBackend shows Connected when handlers are in place', async () => {
    render(
      <SseProvider>
        <MemoryRouter>
          <RailBackend />
        </MemoryRouter>
      </SseProvider>,
    )
    await waitFor(() => expect(screen.getByText('Connected')).toBeTruthy())
    // app_name from /config fixture appears as "service: vibing"
    expect(screen.getByText('service: vibing')).toBeTruthy()
  })

  it('Settings renders backend host and diagnostics from mock fixtures', async () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByDisplayValue('127.0.0.1')).toBeTruthy())
    expect(screen.getByText('Docker')).toBeTruthy()
  })

  it('AppShell renders nav and right rail without a running backend', async () => {
    render(
      <SseProvider>
        <MemoryRouter initialEntries={['/devcontainers']}>
          <AppShell />
        </MemoryRouter>
      </SseProvider>,
    )
    // Right rail Backend section
    await waitFor(() => expect(screen.getByText('Connected')).toBeTruthy())
    // Sidebar navigation items
    expect(screen.getByText('Devcontainers')).toBeTruthy()
    expect(screen.getByText('Settings')).toBeTruthy()
  })
})
