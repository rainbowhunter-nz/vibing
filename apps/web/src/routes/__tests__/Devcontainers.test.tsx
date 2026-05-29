import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { Devcontainers } from '../Devcontainers'
import { fetchDevcontainers } from '../../lib/api'

vi.mock('../../lib/api/endpoints')
const mockFetch = vi.mocked(fetchDevcontainers)

function renderPage() {
  return render(
    <MemoryRouter>
      <Devcontainers />
    </MemoryRouter>,
  )
}

beforeEach(() => vi.clearAllMocks())

const sample = {
  id: 'dc1',
  name: 'my-project',
  local_path: '/home/me/my-project',
  status: 'stopped',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

describe('Devcontainers', () => {
  it('shows the spinner while loading', () => {
    mockFetch.mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('shows the error state when the fetch rejects', async () => {
    mockFetch.mockRejectedValue(new Error('down'))
    renderPage()
    await waitFor(() => expect(screen.getByText("Couldn't load devcontainers")).toBeTruthy())
  })

  it('shows the empty state when there are no devcontainers', async () => {
    mockFetch.mockResolvedValue({ items: [] })
    renderPage()
    await waitFor(() => expect(screen.getByText('No devcontainers yet')).toBeTruthy())
  })

  it('lists devcontainers when ready', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    renderPage()
    await waitFor(() => expect(screen.getByText('my-project')).toBeTruthy())
  })
})
