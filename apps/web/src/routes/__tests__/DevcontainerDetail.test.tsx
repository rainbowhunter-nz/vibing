import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { DevcontainerDetail } from '../DevcontainerDetail'
import { fetchDevcontainer } from '../../lib/api/endpoints'
import { ApiError } from '../../lib/api'
import type { Devcontainer } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockFetch = vi.mocked(fetchDevcontainer)

function renderPage(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/devcontainers/${id}`]}>
      <Routes>
        <Route path="/devcontainers/:id" element={<DevcontainerDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => cleanup())

const sample: Devcontainer = {
  id: 'dc1',
  name: 'my-project',
  local_path: '/home/me/my-project',
  status: 'stopped',
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-16T12:30:00Z',
}

describe('DevcontainerDetail', () => {
  it('shows loading spinner while fetching', () => {
    mockFetch.mockReturnValue(new Promise(() => {}))
    renderPage('dc1')
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('fetches the devcontainer by id and renders details when ready', async () => {
    mockFetch.mockResolvedValue(sample)
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
    renderPage('dc1')
    await waitFor(() => expect(screen.getByText("Couldn't load devcontainer")).toBeTruthy())
  })

  it('shows not-found state when backend returns 404 DEVCONTAINER_NOT_FOUND', async () => {
    mockFetch.mockRejectedValue(new ApiError(404, 'DEVCONTAINER_NOT_FOUND', 'Not found'))
    renderPage('dc1')
    await waitFor(() => expect(screen.getByText('Devcontainer not found')).toBeTruthy())
    expect(screen.getByText("This devcontainer doesn't exist or has been deleted.")).toBeTruthy()
  })
})
