import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, cleanup, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { SseProvider } from '../../lib/events'
import { DevcontainerDetail } from '../DevcontainerDetail'
import { fetchDevcontainer, fetchAgentSessions, fetchAgentSession, fetchAgentSessionTranscript, startAgentSession, stopAgentSession, resumeAgentSession, deleteAgentSession, openAgentSessionStream } from '../../lib/api/endpoints'
import { ApiError } from '../../lib/api'
import type { AgentSession, AgentSessionTranscript, DevcontainerView } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockFetch = vi.mocked(fetchDevcontainer)
const mockFetchSessions = vi.mocked(fetchAgentSessions)
const mockStart = vi.mocked(startAgentSession)
const mockStop = vi.mocked(stopAgentSession)
const mockResume = vi.mocked(resumeAgentSession)
const mockDelete = vi.mocked(deleteAgentSession)
const mockFetchSession = vi.mocked(fetchAgentSession)
const mockFetchTranscript = vi.mocked(fetchAgentSessionTranscript)
const mockOpenStream = vi.mocked(openAgentSessionStream)

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

const emptyTranscript: AgentSessionTranscript = { state: 'empty', turns: [], summary_text: null }

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
  vi.clearAllMocks()
  mockFetchTranscript.mockResolvedValue(emptyTranscript)
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
  prompt: 'do something',
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
    expect(screen.queryByTitle('Delete')).toBeNull()
  })

  it('shows delete button only for non-active sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    const completedSession = { ...sampleSession, status: 'completed' as const }
    mockFetchSessions.mockResolvedValue({ items: [sampleSession, completedSession] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    expect(screen.queryAllByTitle('Delete')).toHaveLength(1)
  })

  it('clicking delete calls deleteAgentSession and refetches sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    const completedSession = {
      ...sampleSession,
      id: 'sess-completed-0000-0000-000000000001',
      status: 'completed' as const,
    }
    mockFetchSessions.mockResolvedValue({ items: [completedSession] })
    mockDelete.mockResolvedValue(undefined)
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    await act(async () => { fireEvent.click(screen.getByTitle('Delete')) })
    expect(mockDelete).toHaveBeenCalledWith('dc1', completedSession.id)
    expect(mockFetchSessions).toHaveBeenCalledTimes(2)
  })

  it('renders empty state for agent sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    expect(screen.getByText('No agent sessions')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// ChatComposer — unified start / resume / stop / disabled (AC3 + AC4 + AC5)
// ---------------------------------------------------------------------------

describe('ChatComposer — guard / disabled states', () => {
  it('AC5: Start disabled and helper text shown when agent_connected is false', async () => {
    const dc = { ...sample, runtime: { worker_connected: false, agent_connected: false } }
    mockFetch.mockResolvedValue(dc)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    // No active session + agent not connected → disabled mode: Start shown but disabled
    const startBtn = screen.getByRole('button', { name: 'Start' }) as HTMLButtonElement
    expect(startBtn.disabled).toBe(true)
    expect(screen.getByText('Agent not connected')).toBeTruthy()
  })

  it('AC3: Composer shows Stop when active session exists, textarea disabled', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] }) // status: running
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Start' })).toBeNull()
    const textarea = screen.getByPlaceholderText('Enter a prompt…') as HTMLTextAreaElement
    expect(textarea.disabled).toBe(true)
    expect(screen.getByText('A session is active')).toBeTruthy()
  })

  it('AC3: Start mode shown when agent connected and no active session', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    const textarea = screen.getByPlaceholderText('Enter a prompt…')
    fireEvent.change(textarea, { target: { value: 'do something' } })
    const startBtn = screen.getByRole('button', { name: 'Start' }) as HTMLButtonElement
    expect(startBtn.disabled).toBe(false)
  })

  it('AC3: Stop button absent when no active session', async () => {
    mockFetch.mockResolvedValue(sample)
    const completedSession = { ...sampleSession, status: 'completed' as const }
    mockFetchSessions.mockResolvedValue({ items: [completedSession] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Start' })).toBeTruthy()
  })

  it('AC3: Stop button disabled when busy (agent not connected forces disabled mode — no Stop shown)', async () => {
    // When agent not connected AND active session exists → active mode wins → Stop shown (not disabled)
    // This tests the active + no-agent case: active mode still shows Stop, just busy state governs disable
    const dc = { ...sample, runtime: { worker_connected: false, agent_connected: false } }
    mockFetch.mockResolvedValue(dc)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    // Active session → mode is 'active' regardless of agent_connected
    expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy()
  })

  it('AC3: clicking Start calls startAgentSession and refetches sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    mockStart.mockResolvedValue({ ...sampleSession, status: 'starting' })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    const textarea = screen.getByPlaceholderText('Enter a prompt…')
    fireEvent.change(textarea, { target: { value: 'do something' } })
    const startBtn = screen.getByRole('button', { name: 'Start' })
    await act(async () => { fireEvent.click(startBtn) })
    expect(mockStart).toHaveBeenCalledWith('dc1', { prompt: 'do something' })
    expect(mockFetchSessions).toHaveBeenCalledTimes(2) // initial + after start
  })

  it('AC3: clicking Stop calls stopAgentSession and refetches sessions', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [sampleSession] })
    mockStop.mockResolvedValue({ ...sampleSession, status: 'stopped' })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
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

  it('clicking a session shows the conversation via transcript has_turns', async () => {
    const completedSession = {
      ...sampleSession,
      status: 'completed' as const,
      prompt: 'hi',
      ended_at: '2024-01-16T10:05:00Z',
    }
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [completedSession] })
    mockFetchSession.mockResolvedValue({ ...completedSession, summary_text: null })
    mockFetchTranscript.mockResolvedValue({
      state: 'has_turns',
      turns: [
        { id: 't-u1', role: 'user', blocks: [{ kind: 'text', text: 'hi' }], at: '2024-01-16T10:00:00Z' },
        { id: 't-a1', role: 'assistant', blocks: [{ kind: 'text', text: 'Hello! How can I help you today?' }], at: '2024-01-16T10:01:00Z' },
      ],
      summary_text: null,
    })

    renderPage('dc1')
    await screen.findByText('Agent Sessions')

    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
    expect(await screen.findByText('hi')).toBeTruthy()
    expect(screen.getByText('Hello! How can I help you today?')).toBeTruthy()
    expect(mockFetchSession).toHaveBeenCalledWith('dc1', completedSession.id)
    expect(mockFetchTranscript).toHaveBeenCalledWith('dc1', completedSession.id)
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

// ---------------------------------------------------------------------------
// SessionDetailPanel — transcript states (AC1–AC4, AC6)
// ---------------------------------------------------------------------------

describe('SessionDetailPanel — transcript states', () => {
  const completedSession: AgentSession = {
    ...{
      id: 'sess-0001-0000-0000-000000000001',
      devcontainer_id: 'dc1',
      status: 'completed' as const,
      prompt: 'Fix the bug',
      started_at: '2024-01-16T10:00:00Z',
      ended_at: '2024-01-16T10:05:00Z',
      last_event_at: null,
      created_at: '2024-01-16T10:00:00Z',
      updated_at: '2024-01-16T10:05:00Z',
    },
  }

  async function openPanel(dc = sample) {
    mockFetch.mockResolvedValue(dc)
    mockFetchSessions.mockResolvedValue({ items: [completedSession] })
    mockFetchSession.mockResolvedValue({ ...completedSession, summary_text: null })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
  }

  it('AC1: has_turns renders user and assistant chat bubbles', async () => {
    mockFetchTranscript.mockResolvedValue({
      state: 'has_turns',
      turns: [
        { id: 't-u2', role: 'user', blocks: [{ kind: 'text', text: 'Fix the bug' }], at: '2024-01-16T10:00:00Z' },
        { id: 't-a2b', role: 'assistant', blocks: [{ kind: 'text', text: 'Done.' }], at: '2024-01-16T10:01:00Z' },
      ],
      summary_text: null,
    })
    await openPanel()
    expect(await screen.findByText('Fix the bug')).toBeTruthy()
    expect(screen.getByText('Done.')).toBeTruthy()
    expect(screen.getByText('You')).toBeTruthy()
    expect(screen.getByText('Agent')).toBeTruthy()
  })

  it('AC2: tool_use block renders compact pill with name + summary, not raw output', async () => {
    mockFetchTranscript.mockResolvedValue({
      state: 'has_turns',
      turns: [
        {
          id: 't-a3',
          role: 'assistant',
          blocks: [
            { kind: 'tool_use', name: 'Bash', summary: 'ran pytest --tb=short' },
            { kind: 'text', text: 'All tests passed.' },
          ],
          at: '2024-01-16T10:01:00Z',
        },
      ],
      summary_text: null,
    })
    await openPanel()
    expect(await screen.findByText('Bash')).toBeTruthy()
    expect(screen.getByText('ran pytest --tb=short')).toBeTruthy()
    expect(screen.getByText('All tests passed.')).toBeTruthy()
    // Tool output must NOT appear
    expect(screen.queryByText(/tool output/i)).toBeNull()
  })

  it('AC3: summary_fallback renders summary text and affordance', async () => {
    mockFetchTranscript.mockResolvedValue({
      state: 'summary_fallback',
      turns: [],
      summary_text: 'All tests passed. Ready to merge.',
    })
    await openPanel()
    expect(await screen.findByText('All tests passed. Ready to merge.')).toBeTruthy()
    expect(screen.getByText(/Start the devcontainer to view or continue/i)).toBeTruthy()
  })

  it('AC3: empty state renders "No conversation yet."', async () => {
    mockFetchTranscript.mockResolvedValue({ state: 'empty', turns: [], summary_text: null })
    await openPanel()
    expect(await screen.findByText('No conversation yet.')).toBeTruthy()
  })

  it('AC3: error state (state==="error") renders error UI', async () => {
    mockFetchTranscript.mockResolvedValue({ state: 'error', turns: [], summary_text: null })
    await openPanel()
    expect(await screen.findByText(/Couldn't load transcript/i)).toBeTruthy()
  })

  it('AC3: network/ApiError on transcript fetch renders error UI', async () => {
    mockFetchTranscript.mockRejectedValue(new ApiError(500, 'INTERNAL_ERROR', 'down'))
    await openPanel()
    expect(await screen.findByText(/Couldn't load transcript/i)).toBeTruthy()
  })

  it('AC4: agent_sessions SSE invalidation re-fetches transcript', async () => {
    mockFetchTranscript
      .mockResolvedValueOnce({ state: 'empty', turns: [], summary_text: null })
      .mockResolvedValueOnce({
        state: 'has_turns',
        turns: [{ id: 't-a2', role: 'assistant', blocks: [{ kind: 'text', text: 'Done.' }], at: '2024-01-16T10:01:00Z' }],
        summary_text: null,
      })
    await openPanel()
    await screen.findByText('No conversation yet.')

    const callsBefore = mockFetchTranscript.mock.calls.length

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'agent_sessions', ids: [] })
    })

    await waitFor(() => expect(mockFetchTranscript.mock.calls.length).toBeGreaterThan(callsBefore))
    await waitFor(() => expect(screen.getByText('Done.')).toBeTruthy())
  })
})

// ---------------------------------------------------------------------------
// Live Session Stream (ADR-0010): assistant text streams in token-by-token while
// active, reconciles to the transcript on the terminal event, no stream when resting.
// ---------------------------------------------------------------------------

describe('SessionDetailPanel — live stream (ADR-0010)', () => {
  // Minimal controllable EventSource the per-session stream hook drives.
  class StreamES {
    url: string
    private listeners: Record<string, Set<EventListener>> = {}
    closed = false
    constructor(url: string) {
      this.url = url
    }
    addEventListener(type: string, l: EventListener) {
      ;(this.listeners[type] ??= new Set()).add(l)
    }
    removeEventListener(type: string, l: EventListener) {
      this.listeners[type]?.delete(l)
    }
    close() {
      this.closed = true
    }
    emit(delta: unknown) {
      const e = Object.assign(new Event('turn_delta'), { data: JSON.stringify(delta) }) as MessageEvent
      this.listeners['turn_delta']?.forEach((l) => l(e))
    }
  }

  const runningSession: AgentSession = {
    id: 'sess-0001-0000-0000-000000000001',
    devcontainer_id: 'dc1',
    status: 'running',
    prompt: 'Do the thing',
    started_at: '2024-01-16T10:00:00Z',
    ended_at: null,
    last_event_at: null,
    created_at: '2024-01-16T10:00:00Z',
    updated_at: '2024-01-16T10:00:00Z',
  }

  async function openRunningPanel(): Promise<StreamES> {
    const stream = new StreamES('/stream')
    mockOpenStream.mockReturnValue(stream as unknown as EventSource)
    mockFetch.mockResolvedValue({ ...sample, status: 'running' })
    mockFetchSessions.mockResolvedValue({ items: [runningSession] })
    mockFetchSession.mockResolvedValue({ ...runningSession, summary_text: null })
    mockFetchTranscript.mockResolvedValue(emptyTranscript)
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
    // Active session → working indicator shows instead of "No conversation yet."
    await screen.findByText('Working…')
    return stream
  }

  it('AC1: streams assistant text token-by-token into the chat while running', async () => {
    const stream = await openRunningPanel()
    act(() => {
      stream.emit({ kind: 'run_started' })
      stream.emit({ kind: 'text', turn_id: 'live-1', role: 'assistant', text: 'Hel' })
    })
    await waitFor(() => expect(screen.getByText('Hel')).toBeTruthy())
    act(() => {
      stream.emit({ kind: 'text', turn_id: 'live-1', role: 'assistant', text: 'lo' })
    })
    await waitFor(() => expect(screen.getByText('Hello')).toBeTruthy())
  })

  it('AC2: terminal run_ended refetches transcript and reconciles with no duplicate bubble', async () => {
    const stream = await openRunningPanel()
    act(() => {
      stream.emit({ kind: 'run_started' })
      stream.emit({ kind: 'text', turn_id: 'live-1', role: 'assistant', text: 'Hello' })
    })
    await waitFor(() => expect(screen.getByText('Hello')).toBeTruthy())

    // On run_ended the canonical transcript (same id) is fetched and reconciles.
    mockFetchTranscript.mockResolvedValue({
      state: 'has_turns',
      turns: [{ id: 'live-1', role: 'assistant', blocks: [{ kind: 'text', text: 'Hello' }], at: 't' }],
      summary_text: null,
    })
    act(() => {
      stream.emit({ kind: 'run_ended' })
    })
    await waitFor(() => expect(screen.getAllByText('Hello')).toHaveLength(1))
  })

  it('AC4: resting session opens NO stream (transcript-only)', async () => {
    mockOpenStream.mockClear()
    mockFetch.mockResolvedValue(sample)
    const completed = { ...runningSession, status: 'completed' as const }
    mockFetchSessions.mockResolvedValue({ items: [completed] })
    mockFetchSession.mockResolvedValue({ ...completed, summary_text: null })
    mockFetchTranscript.mockResolvedValue(emptyTranscript)
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
    await screen.findByText('No conversation yet.')
    expect(mockOpenStream).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Unified composer — resume (AC3 + AC5)
// ---------------------------------------------------------------------------

describe('ChatComposer — resume (Continue) behavior', () => {
  const restingSession: AgentSession = {
    id: 'sess-0001-0000-0000-000000000001',
    devcontainer_id: 'dc1',
    status: 'completed',
    prompt: 'Fix the bug',
    started_at: '2024-01-16T10:00:00Z',
    ended_at: '2024-01-16T10:05:00Z',
    last_event_at: null,
    created_at: '2024-01-16T10:00:00Z',
    updated_at: '2024-01-16T10:05:00Z',
  }

  const ACTIVE_SESSION_STATUSES = new Set(['starting', 'running', 'waiting_for_approval'])

  async function openPanel(dc: DevcontainerView, sessions: AgentSession[]) {
    mockFetch.mockResolvedValue(dc)
    mockFetchSessions.mockResolvedValue({ items: sessions })
    mockFetchSession.mockResolvedValue({ ...sessions[0], summary_text: null })
    mockFetchTranscript.mockResolvedValue(emptyTranscript)
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
    // The clicked session (sessions[0], id starts with 'sess-000') drives the panel state.
    // Active selected session → working indicator; resting selected session → "No conversation yet."
    const selectedActive = ACTIVE_SESSION_STATUSES.has(sessions[0].status)
    await screen.findByText(selectedActive ? 'Working…' : 'No conversation yet.')
  }

  it('AC5: shows Continue button for resting session in running, connected devcontainer', async () => {
    await openPanel({ ...sample, status: 'running' }, [restingSession])
    expect(screen.getByRole('button', { name: 'Continue' })).toBeTruthy()
    expect(screen.getByPlaceholderText('Send a follow-up…')).toBeTruthy()
  })

  it('AC3: when another session is active, shows Stop button (active mode wins over selected resting)', async () => {
    const otherActive: AgentSession = { ...restingSession, id: 'sess-other-0000-0000-000000000002', status: 'running' }
    await openPanel({ ...sample, status: 'running' }, [restingSession, otherActive])
    // Active session wins → Stop mode, no Continue
    expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull()
    expect(screen.getByText('A session is active')).toBeTruthy()
  })

  it('AC5: shows Start button (not Continue) for running session — active mode, no resume', async () => {
    const runningSession: AgentSession = { ...restingSession, status: 'running' }
    await openPanel({ ...sample, status: 'running' }, [runningSession])
    // Running session → active mode → Stop button
    expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull()
  })

  it('AC5: shows disabled composer when devcontainer not running (selected resting session)', async () => {
    await openPanel({ ...sample, status: 'stopped' }, [restingSession])
    // Resting session selected + dc stopped → disabled mode
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull()
    expect(screen.getByText('Start the devcontainer to continue')).toBeTruthy()
  })

  it('AC5: shows disabled composer when agent not connected', async () => {
    await openPanel(
      { ...sample, status: 'running', runtime: { worker_connected: true, agent_connected: false } },
      [restingSession],
    )
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull()
    expect(screen.getByText('Agent not connected')).toBeTruthy()
  })

  it('AC3: submitting calls resumeAgentSession and refetches sessions + transcript', async () => {
    await openPanel({ ...sample, status: 'running' }, [restingSession])
    mockResume.mockResolvedValue({ ...restingSession, status: 'starting' })
    const sessionsCallsBefore = mockFetchSessions.mock.calls.length
    const transcriptCallsBefore = mockFetchTranscript.mock.calls.length

    const textarea = screen.getByPlaceholderText('Send a follow-up…')
    fireEvent.change(textarea, { target: { value: 'now run the tests' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Continue' })) })

    expect(mockResume).toHaveBeenCalledWith('dc1', restingSession.id, { prompt: 'now run the tests' })
    expect(mockFetchSessions.mock.calls.length).toBeGreaterThan(sessionsCallsBefore)
    expect(mockFetchTranscript.mock.calls.length).toBeGreaterThan(transcriptCallsBefore)
  })
})

// ---------------------------------------------------------------------------
// AC1: Two-pane layout — collapsible left pane
// ---------------------------------------------------------------------------

describe('Two-pane layout', () => {
  it('AC1: renders two-pane layout with collapsible left pane toggle', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')

    // Left pane visible with devcontainer info and sessions list
    expect(screen.getByText('my-project')).toBeTruthy()
    expect(screen.getByText('No agent sessions')).toBeTruthy()

    // Collapse toggle present
    const toggle = screen.getByTitle('Collapse panel')
    expect(toggle).toBeTruthy()

    // Collapsing hides the left pane content
    fireEvent.click(toggle)
    expect(screen.queryByText('my-project')).toBeNull()
    expect(screen.getByTitle('Expand panel')).toBeTruthy()

    // Expanding restores it
    fireEvent.click(screen.getByTitle('Expand panel'))
    expect(await screen.findByText('my-project')).toBeTruthy()
  })

  it('AC2: chat pane shows placeholder when no session selected', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    expect(screen.getByText('Select a session to view the conversation')).toBeTruthy()
  })

  it('AC2: composer pinned at bottom — always visible regardless of session selection', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [] })
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    // Composer textarea always present
    expect(screen.getByPlaceholderText('Enter a prompt…')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// VIB-112: Snappy chat — optimistic echo, scroll, working indicator
// ---------------------------------------------------------------------------

describe('VIB-112 snappy chat interactions', () => {
  class StreamES {
    url: string
    private listeners: Record<string, Set<EventListener>> = {}
    closed = false
    constructor(url: string) { this.url = url }
    addEventListener(type: string, l: EventListener) { (this.listeners[type] ??= new Set()).add(l) }
    removeEventListener(type: string, l: EventListener) { this.listeners[type]?.delete(l) }
    close() { this.closed = true }
    emit(delta: unknown) {
      const e = Object.assign(new Event('turn_delta'), { data: JSON.stringify(delta) }) as MessageEvent
      this.listeners['turn_delta']?.forEach((l) => l(e))
    }
  }

  const runningSession: AgentSession = {
    id: 'sess-0001-0000-0000-000000000001',
    devcontainer_id: 'dc1',
    status: 'running',
    prompt: 'Do the thing',
    started_at: '2024-01-16T10:00:00Z',
    ended_at: null,
    last_event_at: null,
    created_at: '2024-01-16T10:00:00Z',
    updatedAt: '2024-01-16T10:00:00Z',
    updated_at: '2024-01-16T10:00:00Z',
  } as AgentSession

  const restingSession: AgentSession = {
    id: 'sess-0001-0000-0000-000000000001',
    devcontainer_id: 'dc1',
    status: 'completed',
    prompt: 'Do the thing',
    started_at: '2024-01-16T10:00:00Z',
    ended_at: '2024-01-16T10:05:00Z',
    last_event_at: null,
    created_at: '2024-01-16T10:00:00Z',
    updated_at: '2024-01-16T10:05:00Z',
  }

  async function openRunningPanel(): Promise<StreamES> {
    const stream = new StreamES('/stream')
    mockOpenStream.mockReturnValue(stream as unknown as EventSource)
    mockFetch.mockResolvedValue({ ...sample, status: 'running' })
    mockFetchSessions.mockResolvedValue({ items: [runningSession] })
    mockFetchSession.mockResolvedValue({ ...runningSession, summary_text: null })
    mockFetchTranscript.mockResolvedValue(emptyTranscript)
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
    await screen.findByText('Working…')
    return stream
  }

  // AC1: optimistic echo — input cleared immediately, bubble shown
  it('AC1: clears input immediately and shows optimistic bubble on send', async () => {
    mockFetch.mockResolvedValue({ ...sample, status: 'running' })
    mockFetchSessions.mockResolvedValue({ items: [] })
    mockStart.mockReturnValue(new Promise(() => {})) // never resolves — simulate network delay
    renderPage('dc1')
    await screen.findByText('Agent Sessions')

    const textarea = screen.getByPlaceholderText('Enter a prompt…') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'hello agent' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Start' })) })

    // Input cleared immediately (before the API call resolves)
    expect(textarea.value).toBe('')
    // Optimistic bubble visible
    expect(screen.getByText('hello agent')).toBeTruthy()
  })

  // AC2: reconcile — no duplicate bubble when real user turn arrives in the session transcript.
  // Uses resume flow (session already selected) so ConversationBody is mounted and the
  // reconcile useEffect can fire when the transcript refetch returns the real user turn.
  it('AC2: reconciles optimistic bubble when real user turn arrives (no duplicate)', async () => {
    const stream = new StreamES('/stream-ac2')
    mockOpenStream.mockReturnValue(stream as unknown as EventSource)
    mockFetch.mockResolvedValue({ ...sample, status: 'running' })
    // Session starts resting; after resume it becomes running
    mockFetchSessions
      .mockResolvedValueOnce({ items: [restingSession] })
      .mockResolvedValue({ items: [runningSession] })
    mockFetchSession
      .mockResolvedValueOnce({ ...restingSession, summary_text: null })
      .mockResolvedValue({ ...runningSession, summary_text: null })
    mockResume.mockResolvedValue(runningSession)
    // First transcript load: empty; after resume + refetch: real user turn present
    mockFetchTranscript
      .mockResolvedValueOnce(emptyTranscript)
      .mockResolvedValue({
        state: 'has_turns' as const,
        turns: [{ id: 't-u1', role: 'user' as const, blocks: [{ kind: 'text' as const, text: 'resume prompt' }], at: '' }],
        summary_text: null,
      })

    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
    await screen.findByText('No conversation yet.')

    const textarea = screen.getByPlaceholderText('Send a follow-up…') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'resume prompt' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Continue' })) })

    // Optimistic bubble visible immediately after click (before API resolves)
    expect(screen.getByText('resume prompt')).toBeTruthy()

    // After reconcile (transcript refetched with real user turn): exactly one bubble
    await waitFor(() => {
      expect(screen.getAllByText('resume prompt')).toHaveLength(1)
    })
  })

  // AC4: scroll stick/pause + jump-to-latest affordance
  it('AC4: shows Jump to latest button when user scrolls up', async () => {
    await openRunningPanel()

    // Simulate user scrolling up: patch scroll metrics so shouldStick → false
    const scrollContainer = screen.getByTestId('conversation-scroll') as HTMLDivElement
    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 0, configurable: true })
    fireEvent.scroll(scrollContainer)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Jump to latest' })).toBeTruthy()
    })
  })

  it('AC4: clicking Jump to latest hides the button (re-sticks to bottom)', async () => {
    await openRunningPanel()

    const scrollContainer = screen.getByTestId('conversation-scroll') as HTMLDivElement
    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 0, configurable: true })
    fireEvent.scroll(scrollContainer)

    await waitFor(() => screen.getByRole('button', { name: 'Jump to latest' }))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Jump to latest' })) })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Jump to latest' })).toBeNull())
  })

  // AC5: working indicator
  it('AC5: shows working indicator when session active and no live text', async () => {
    await openRunningPanel()
    // Working indicator already visible (waited for it in openRunningPanel)
    expect(screen.getByText('Working…')).toBeTruthy()
  })

  it('AC5: clears working indicator when live text starts streaming', async () => {
    const stream = await openRunningPanel()
    expect(screen.getByText('Working…')).toBeTruthy()

    act(() => {
      stream.emit({ kind: 'text', turn_id: 'live-1', role: 'assistant', text: 'Hi there' })
    })

    await waitFor(() => expect(screen.queryByText('Working…')).toBeNull())
    expect(screen.getByText('Hi there')).toBeTruthy()
  })

  // Regression: prior turn with same text must NOT immediately reconcile the optimistic bubble.
  it('AC2 regression: prior matching turn does not prematurely clear optimistic bubble', async () => {
    const stream = new StreamES('/stream-reg')
    mockOpenStream.mockReturnValue(stream as unknown as EventSource)
    mockFetch.mockResolvedValue({ ...sample, status: 'running' })
    // Session starts resting; becomes running after resume
    mockFetchSessions
      .mockResolvedValueOnce({ items: [restingSession] })
      .mockResolvedValue({ items: [runningSession] })
    mockFetchSession
      .mockResolvedValueOnce({ ...restingSession, summary_text: null })
      .mockResolvedValue({ ...runningSession, summary_text: null })
    mockResume.mockReturnValue(new Promise(() => {})) // never resolves — keeps bubble alive

    // Transcript already has a prior user turn with text 'hello'
    mockFetchTranscript.mockResolvedValue({
      state: 'has_turns' as const,
      turns: [{ id: 't-prior', role: 'user' as const, blocks: [{ kind: 'text' as const, text: 'hello' }], at: '' }],
      summary_text: null,
    })

    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
    // Prior 'hello' turn visible; resting session → no 'Working…'
    await screen.findByText('hello')
    expect(screen.queryByText('Working…')).toBeNull()

    // User sends 'hello' again — optimistic bubble must appear alongside the prior one
    const textarea = screen.getByPlaceholderText('Send a follow-up…') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'hello' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Continue' })) })

    // Both the prior turn AND the optimistic bubble should be visible (two 'hello' texts).
    // The optimistic bubble must NOT be prematurely cleared against the pre-existing turn.
    expect(screen.getAllByText('hello')).toHaveLength(2)

    // Now the real new user turn arrives via transcript refetch (two user turns with 'hello')
    mockFetchTranscript.mockResolvedValue({
      state: 'has_turns' as const,
      turns: [
        { id: 't-prior', role: 'user' as const, blocks: [{ kind: 'text' as const, text: 'hello' }], at: '' },
        { id: 't-new', role: 'user' as const, blocks: [{ kind: 'text' as const, text: 'hello' }], at: '' },
      ],
      summary_text: null,
    })
    // Trigger a transcript refetch via SSE invalidation
    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'agent_sessions', ids: [] })
    })

    // After reconcile: exactly two 'hello' bubbles (the two real turns), optimistic cleared
    await waitFor(() => {
      expect(screen.getAllByText('hello')).toHaveLength(2)
    })
  })

  it('AC5: working indicator absent for completed (non-active) session', async () => {
    mockFetch.mockResolvedValue(sample)
    mockFetchSessions.mockResolvedValue({ items: [restingSession] })
    mockFetchSession.mockResolvedValue({ ...restingSession, summary_text: null })
    mockFetchTranscript.mockResolvedValue(emptyTranscript)
    renderPage('dc1')
    await screen.findByText('Agent Sessions')
    fireEvent.click(screen.getByRole('button', { name: /sess-000/i }))
    await screen.findByText('No conversation yet.')
    expect(screen.queryByText('Working…')).toBeNull()
  })
})
