import { describe, it, expect, beforeEach } from 'vitest'
import { listHarnesses, authenticateHarness, resetHarnesses, NotFoundError } from '../state/harnesses'

beforeEach(() => resetHarnesses())

describe('harness mock state', () => {
  it('lists seeded harnesses for a devcontainer', () => {
    const { items } = listHarnesses('dc-seed-0001')
    expect(items.map((h) => h.name)).toEqual(['claude-code', 'codex', 'cursor'])
  })

  it('returns empty items for an unseeded devcontainer', () => {
    expect(listHarnesses('dc-unknown').items).toEqual([])
  })

  it('authenticate flips authenticated=true and persists', () => {
    expect(authenticateHarness('dc-seed-0001', 'codex').authenticated).toBe(true)
    expect(listHarnesses('dc-seed-0001').items.find((h) => h.name === 'codex')!.authenticated).toBe(true)
  })

  it('throws NotFoundError for an unknown harness', () => {
    expect(() => authenticateHarness('dc-seed-0001', 'nope')).toThrow(NotFoundError)
  })

  it('resetHarnesses restores seed state', () => {
    authenticateHarness('dc-seed-0001', 'codex')
    resetHarnesses()
    expect(listHarnesses('dc-seed-0001').items.find((h) => h.name === 'codex')!.authenticated).toBe(false)
  })
})
