import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { HarnessList } from '../HarnessList'
import type { HarnessStatus } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints', () => ({
  installHarness: vi.fn().mockResolvedValue(undefined),
  authenticateHarness: vi.fn().mockResolvedValue(undefined),
  refreshHarnesses: vi.fn().mockResolvedValue({ items: [], known: true }),
}))

const harnesses: HarnessStatus[] = [
  { name: 'claude-code', installed: true, authenticated: true },
  { name: 'codex', installed: true, authenticated: false },
  { name: 'cursor', installed: false, authenticated: false },
]

afterEach(cleanup)

function setup() {
  render(<HarnessList devcontainerId="dc-seed-0001" harnesses={harnesses} known running onChange={() => {}} />)
}

describe('HarnessList', () => {
  it('renders a row per harness', () => {
    setup()
    expect(screen.getByText('claude-code')).toBeTruthy()
    expect(screen.getByText('codex')).toBeTruthy()
    expect(screen.getByText('cursor')).toBeTruthy()
  })

  it('offers Authenticate on an installed-but-unauthenticated harness', () => {
    setup()
    expect((screen.getByTitle('Authenticate codex') as HTMLButtonElement).disabled).toBe(false)
  })

  it('offers Install on a not-installed harness', () => {
    setup()
    expect(screen.getByTitle('Install cursor')).toBeTruthy()
  })

  it('greys out Authenticate until the harness is installed', () => {
    setup()
    expect((screen.getByTitle('Install cursor first') as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows a check tick for an authenticated harness', () => {
    setup()
    expect(screen.getByTitle('Authenticated')).toBeTruthy()
  })

  it('shows a tick for installed harnesses', () => {
    setup()
    expect(screen.getAllByTitle('Installed').length).toBe(2)
  })

  it('shows container-scoped message when the container is not running', () => {
    render(<HarnessList devcontainerId="dc-seed-0002" harnesses={[]} known={false} running={false} onChange={() => {}} />)
    expect(screen.getByText(/container not running — harness status unavailable/i)).toBeTruthy()
  })

  it('shows a loading spinner while a running container recomputes status', () => {
    render(<HarnessList devcontainerId="dc-seed-0002" harnesses={[]} known={false} running onChange={() => {}} />)
    expect(screen.getByTestId('spinner-harness')).toBeTruthy()
  })

  it('renders a refresh button', () => {
    setup()
    expect(screen.getByTestId('harness-refresh')).toBeTruthy()
  })

  it('disables the refresh button while refreshing', () => {
    const onChangeFn = vi.fn()
    render(
      <HarnessList
        devcontainerId="dc-seed-0001"
        harnesses={harnesses}
        known
        running
        onChange={onChangeFn}
      />,
    )
    const btn = screen.getByTestId('harness-refresh')
    expect((btn as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(btn)
    // Button should be busy immediately after click
    expect((btn as HTMLButtonElement).disabled).toBe(true)
  })
})
