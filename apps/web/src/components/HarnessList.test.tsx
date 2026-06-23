import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { HarnessList } from './HarnessList'

vi.mock('../lib/api/endpoints', () => ({
  installHarness: vi.fn().mockResolvedValue(undefined),
  authenticateHarness: vi.fn().mockResolvedValue(undefined),
  refreshHarnesses: vi.fn().mockResolvedValue({ items: [], known: true }),
}))

describe('HarnessList', () => {
  it('shows container-scoped message when container is not running', () => {
    render(<HarnessList devcontainerId="dc-1" harnesses={[]} known={false} onChange={() => {}} />)
    expect(screen.getByText(/container not running/i)).toBeTruthy()
  })

  it('keeps spinner after install click until prop flips installed', async () => {
    const h = [{ name: 'codex', installed: false, authenticated: false }]
    const { rerender } = render(
      <HarnessList devcontainerId="dc-1" harnesses={h} known onChange={() => {}} />,
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
        onChange={() => {}}
      />,
    )
    expect(screen.queryByTestId('spinner-install-codex')).toBeNull()
  })
})
