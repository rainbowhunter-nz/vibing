import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { SseProvider } from '../../lib/events'
import { RailActivity } from '../RailActivity'
import { fetchDelegatedRuns } from '../../lib/api'
import type { DelegatedRun } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockRuns = vi.mocked(fetchDelegatedRuns)

const runs: DelegatedRun[] = [
  { run_id: 'run-9', title: 'refactor auth retry', harness: 'claude-code', model: 'opus-4.8', status: 'running', result: null, error: null, started_at: '2024-01-15T10:20:00.000Z' },
  { run_id: 'run-3', title: 'add parser tests', harness: 'cursor', model: 'auto', status: 'completed', result: 'done', error: null, started_at: '2024-01-15T09:55:00.000Z' },
]

function renderAt(path: string) {
  return render(
    <SseProvider>
      <MemoryRouter initialEntries={[path]}>
        <RailActivity />
      </MemoryRouter>
    </SseProvider>,
  )
}

class StubEventSource {
  addEventListener() {}
  removeEventListener() {}
  close() {}
}

beforeEach(() => vi.stubGlobal('EventSource', StubEventSource))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('RailActivity', () => {
  it('shows only running runs for the current devcontainer, title + run_id · harness · model', async () => {
    mockRuns.mockResolvedValue({ items: runs })
    renderAt('/devcontainers/dc-1')

    await waitFor(() => expect(screen.getByText('refactor auth retry')).toBeTruthy())
    expect(screen.getByText('run-9 · claude-code · opus-4.8')).toBeTruthy()
    expect(screen.queryByText('add parser tests')).toBeNull()
    expect(mockRuns).toHaveBeenCalledWith('dc-1')
  })

  it('renders nothing and fetches nothing off a devcontainer detail route', () => {
    const { container } = renderAt('/settings')
    expect(container.firstChild).toBeNull()
    expect(mockRuns).not.toHaveBeenCalled()
  })
})
