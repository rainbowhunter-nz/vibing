import { describe, it, expect, beforeEach } from 'vitest'
import { listDelegatedRuns, resetDelegatedRuns } from '../state/delegatedRuns'

beforeEach(() => resetDelegatedRuns())

describe('delegated-run mock state', () => {
  it('lists seeded runs newest-first as seeded', () => {
    expect(listDelegatedRuns('dc-seed-0001').items.map((r) => r.run_id)).toEqual(['run-9', 'run-8', 'run-7', 'run-6', 'run-4', 'run-3', 'run-2', 'run-1', 'run-0'])
  })

  it('returns empty items for an unseeded devcontainer', () => {
    expect(listDelegatedRuns('dc-unknown').items).toEqual([])
  })
})
