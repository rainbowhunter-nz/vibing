import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { Settings } from '../Settings'
import { fetchSettings, fetchDiagnostics } from '../../lib/api'

vi.mock('../../lib/api/endpoints')
const mockSettings = vi.mocked(fetchSettings)
const mockDiagnostics = vi.mocked(fetchDiagnostics)

beforeEach(() => vi.clearAllMocks())

const settings = {
  backend_host: '127.0.0.1',
  backend_port: 8000,
  runtime: { docker: true, podman: null, devcontainer_cli: null, claude_code: null },
}
const diagnostics = { checks: [{ id: 'docker', label: 'Docker', status: 'ok' as const, message: null }] }

describe('Settings', () => {
  it('shows the spinner while loading', () => {
    mockSettings.mockReturnValue(new Promise(() => {}))
    mockDiagnostics.mockReturnValue(new Promise(() => {}))
    render(<Settings />)
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('shows the error state when a fetch rejects', async () => {
    mockSettings.mockRejectedValue(new Error('down'))
    mockDiagnostics.mockResolvedValue(diagnostics)
    render(<Settings />)
    await waitFor(() => expect(screen.getByText("Couldn't load settings")).toBeTruthy())
  })

  it('renders settings and diagnostics when ready', async () => {
    mockSettings.mockResolvedValue(settings)
    mockDiagnostics.mockResolvedValue(diagnostics)
    render(<Settings />)
    await waitFor(() => expect(screen.getByText('Docker')).toBeTruthy())
    expect(screen.getByDisplayValue('127.0.0.1')).toBeTruthy()
  })
})
