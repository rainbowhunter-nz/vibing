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

  it('offers Install on a not-installed harness', () => {
    setup()
    expect(screen.getByTitle('Install cursor')).toBeTruthy()
  })

  it('disables Authenticate until the harness is installed', () => {
    setup()
    const btn = screen.getByTitle('Install cursor first') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})
