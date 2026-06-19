import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { SseProvider } from '../../lib/events'
import { DevcontainerRuns } from '../DevcontainerRuns'
import { fetchDevcontainer, fetchDelegatedRuns } from '../../lib/api'
import type { DelegatedRun, DevcontainerView } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockDc = vi.mocked(fetchDevcontainer)
const mockRuns = vi.mocked(fetchDelegatedRuns)

const dc: DevcontainerView = {
  id: 'dc-1',
  name: 'my-webapp',
  local_path: '/home/dev/my-webapp',
  status: 'running',
  created_at: '2024-01-10T08:00:00.000Z',
  updated_at: '2024-01-15T10:00:00.000Z',
  runtime: { worker_connected: true, agent_connected: true },
}

const runs: DelegatedRun[] = [
  { run_id: 'run-r', harness: 'codex', model: 'gpt-5-codex', status: 'running', result: null, error: null, started_at: '2024-01-15T10:00:00.000Z' },
  { run_id: 'run-c', harness: 'claude-code', model: 'opus-4.8', status: 'completed', result: 'done', error: null, started_at: '2024-01-15T09:55:00.000Z' },
  { run_id: 'run-f', harness: 'cursor', model: 'auto', status: 'failed', result: null, error: { stderr_tail: 'boom' }, started_at: '2024-01-15T09:40:00.000Z' },
]

function renderPage() {
  return render(
    <SseProvider>
      <MemoryRouter initialEntries={['/devcontainers/dc-1/runs']}>
        <Routes>
          <Route path="devcontainers/:id/runs" element={<DevcontainerRuns />} />
        </Routes>
      </MemoryRouter>
    </SseProvider>,
  )
}

class StubEventSource {
  addEventListener() {}
  removeEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.stubGlobal('EventSource', StubEventSource)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('DevcontainerRuns', () => {
  it('lists every run regardless of status', async () => {
    mockDc.mockResolvedValue(dc)
    mockRuns.mockResolvedValue({ items: runs })
    renderPage()
    await waitFor(() => expect(screen.getByText('run-r')).toBeTruthy())
    expect(screen.getByText('run-c')).toBeTruthy()
    expect(screen.getByText('run-f')).toBeTruthy()
  })

  it('narrows the list when a status filter is selected', async () => {
    mockDc.mockResolvedValue(dc)
    mockRuns.mockResolvedValue({ items: runs })
    renderPage()
    await waitFor(() => expect(screen.getByText('run-r')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'failed 1' }))
    expect(screen.getByText('run-f')).toBeTruthy()
    expect(screen.queryByText('run-r')).toBeNull()
    expect(screen.queryByText('run-c')).toBeNull()
  })
})
