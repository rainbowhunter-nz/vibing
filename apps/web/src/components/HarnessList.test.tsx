import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HarnessList } from './HarnessList'

afterEach(cleanup)

vi.mock('../lib/api/endpoints', () => ({
  installHarness: vi.fn().mockResolvedValue(undefined),
  authenticateHarness: vi.fn().mockResolvedValue(undefined),
  refreshHarnesses: vi.fn().mockResolvedValue({ items: [], known: true }),
}))

describe('HarnessList', () => {
  it('shows container-scoped message when container is not running', () => {
    render(<HarnessList devcontainerId="dc-1" harnesses={[]} known={false} running={false} onChange={() => {}} />)
    expect(screen.getByText(/container not running/i)).toBeTruthy()
  })

  it('hides cached harness rows once the container is not running', () => {
    // Status lifetime is tied to the container: a stopped container shows no rows even
    // if status was previously cached (known=true with items).
    render(
      <HarnessList
        devcontainerId="dc-1"
        harnesses={[{ name: 'codex', installed: true, authenticated: true }]}
        known
        running={false}
        onChange={() => {}}
      />,
    )
    expect(screen.getByText(/container not running/i)).toBeTruthy()
    expect(screen.queryByText('codex')).toBeNull()
  })

  it('shows a spinner while a running container recomputes harness status', () => {
    render(<HarnessList devcontainerId="dc-1" harnesses={[]} known={false} running onChange={() => {}} />)
    expect(screen.getByTestId('spinner-harness')).toBeTruthy()
    expect(screen.queryByText(/container not running/i)).toBeNull()
  })

  it('keeps spinner after install click until prop flips installed', async () => {
    const h = [{ name: 'codex', installed: false, authenticated: false }]
    const { rerender } = render(
      <HarnessList devcontainerId="dc-1" harnesses={h} known running onChange={() => {}} />,
    )
    fireEvent.click(screen.getByTitle('Install codex'))
    // still pending (POST resolved but SSE not yet) → spinner present
    expect(await screen.findByTestId('spinner-install-codex')).toBeTruthy()
    // SSE arrives → parent passes installed:true → spinner gone, check shown
    rerender(
      <HarnessList
        devcontainerId="dc-1"
        harnesses={[{ name: 'codex', installed: true, authenticated: false }]}
        known
        running
        onChange={() => {}}
      />,
    )
    expect(screen.queryByTestId('spinner-install-codex')).toBeNull()
  })
})
