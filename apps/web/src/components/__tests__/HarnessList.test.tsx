import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { HarnessList } from '../HarnessList'
import type { HarnessStatus } from '../../lib/api/types'

const harnesses: HarnessStatus[] = [
  { name: 'claude-code', installed: true, authenticated: true },
  { name: 'codex', installed: true, authenticated: false },
  { name: 'cursor', installed: false, authenticated: false },
]

afterEach(cleanup)

function setup() {
  render(<HarnessList devcontainerId="dc-seed-0001" harnesses={harnesses} onChange={() => {}} />)
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
    expect(screen.getByTitle('Authenticate codex')).toBeTruthy()
  })

  it('offers Authenticate on a not-installed harness (install-on-demand)', () => {
    setup()
    expect(screen.getByTitle('Authenticate cursor')).toBeTruthy()
  })

  it('shows a check tick for an authenticated harness', () => {
    setup()
    expect(screen.getByTitle('Authenticated')).toBeTruthy()
  })
})
