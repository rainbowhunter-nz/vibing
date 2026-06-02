import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { Devcontainers } from '../Devcontainers'
import { fetchDevcontainers, startDevcontainer, stopDevcontainer, deleteDevcontainer } from '../../lib/api'
import type { Devcontainer } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockFetch = vi.mocked(fetchDevcontainers)
const mockStart = vi.mocked(startDevcontainer)
const mockStop = vi.mocked(stopDevcontainer)
const mockDelete = vi.mocked(deleteDevcontainer)

function renderPage() {
  return render(
    <MemoryRouter>
      <Devcontainers />
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
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const runningDc: Devcontainer = { ...sample, id: 'dc2', name: 'running-project', status: 'running' }
const createdDc: Devcontainer = { ...sample, id: 'dc3', name: 'created-project', status: 'created' }
const errorDc: Devcontainer = { ...sample, id: 'dc4', name: 'error-project', status: 'error' }

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

describe('Devcontainers lifecycle buttons', () => {
  it('clicking Start calls startDevcontainer with the correct id', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    mockStart.mockResolvedValue({ ...sample, status: 'starting' })
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByTitle('Start'))
    expect(mockStart).toHaveBeenCalledWith('dc1')
  })

  it('clicking Stop calls stopDevcontainer with the correct id', async () => {
    mockFetch.mockResolvedValue({ items: [runningDc] })
    mockStop.mockResolvedValue({ ...runningDc, status: 'stopping' })
    renderPage()
    await screen.findByText('running-project')

    await userEvent.click(screen.getByTitle('Stop'))
    expect(mockStop).toHaveBeenCalledWith('dc2')
  })

  it('clicking Delete calls deleteDevcontainer with the correct id', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    mockDelete.mockResolvedValue(undefined)
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByTitle('Delete'))
    expect(mockDelete).toHaveBeenCalledWith('dc1')
  })

  it('refetches after a successful start', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    mockStart.mockResolvedValue({ ...sample, status: 'starting' })
    renderPage()
    await screen.findByText('my-project')

    const callsBefore = mockFetch.mock.calls.length
    await userEvent.click(screen.getByTitle('Start'))
    await waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('refetches after a successful stop', async () => {
    mockFetch.mockResolvedValue({ items: [runningDc] })
    mockStop.mockResolvedValue({ ...runningDc, status: 'stopping' })
    renderPage()
    await screen.findByText('running-project')

    const callsBefore = mockFetch.mock.calls.length
    await userEvent.click(screen.getByTitle('Stop'))
    await waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('refetches after a successful delete', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    mockDelete.mockResolvedValue(undefined)
    renderPage()
    await screen.findByText('my-project')

    const callsBefore = mockFetch.mock.calls.length
    await userEvent.click(screen.getByTitle('Delete'))
    await waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('disables buttons while start is in flight', async () => {
    let resolveStart!: (v: Devcontainer) => void
    const deferred = new Promise<Devcontainer>((res) => { resolveStart = res })
    mockFetch.mockResolvedValue({ items: [sample] })
    mockStart.mockReturnValue(deferred)
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByTitle('Start'))
    // While in-flight, both start and stop buttons for that row are disabled
    expect(screen.getByTitle('Start').hasAttribute('disabled')).toBe(true)
    expect(screen.getByTitle('Stop').hasAttribute('disabled')).toBe(true)

    resolveStart({ ...sample, status: 'starting' })
  })

  it('disables delete button while delete is in flight', async () => {
    let resolveDelete!: (v: void) => void
    const deferred = new Promise<void>((res) => { resolveDelete = res })
    mockFetch.mockResolvedValue({ items: [sample] })
    mockDelete.mockReturnValue(deferred)
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByTitle('Delete'))
    expect(screen.getByTitle('Delete').hasAttribute('disabled')).toBe(true)

    resolveDelete()
  })

  it('shows error message when start fails', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    mockStart.mockRejectedValue(new Error('container failed to start'))
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByTitle('Start'))
    await screen.findByText('container failed to start')
  })

  it('shows error message when delete fails', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    mockDelete.mockRejectedValue(new Error('permission denied'))
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByTitle('Delete'))
    await screen.findByText('permission denied')
  })

  it('Start is disabled for a running row', async () => {
    mockFetch.mockResolvedValue({ items: [runningDc] })
    renderPage()
    await screen.findByText('running-project')
    expect(screen.getByTitle('Start').hasAttribute('disabled')).toBe(true)
  })

  it('Stop is disabled for a non-running (stopped) row', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    renderPage()
    await screen.findByText('my-project')
    expect(screen.getByTitle('Stop').hasAttribute('disabled')).toBe(true)
  })

  it('Start is enabled for a created row', async () => {
    mockFetch.mockResolvedValue({ items: [createdDc] })
    renderPage()
    await screen.findByText('created-project')
    expect(screen.getByTitle('Start').hasAttribute('disabled')).toBe(false)
  })

  it('Start is enabled for an error row', async () => {
    mockFetch.mockResolvedValue({ items: [errorDc] })
    renderPage()
    await screen.findByText('error-project')
    expect(screen.getByTitle('Start').hasAttribute('disabled')).toBe(false)
  })
})
