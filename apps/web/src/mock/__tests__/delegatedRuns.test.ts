import { describe, it, expect, beforeEach } from 'vitest'
import { listDelegatedRuns, stopDelegatedRun, resetDelegatedRuns, NotFoundError } from '../state/delegatedRuns'

beforeEach(() => resetDelegatedRuns())

describe('delegated-run mock state', () => {
  it('lists seeded runs newest-first as seeded', () => {
    expect(listDelegatedRuns('dc-seed-0001').items.map((r) => r.run_id)).toEqual(['run-4', 'run-3', 'run-2'])
  })

  it('returns empty items for an unseeded devcontainer', () => {
    expect(listDelegatedRuns('dc-unknown').items).toEqual([])
  })

  it('stop flips a running run to stopped and persists', () => {
    expect(stopDelegatedRun('dc-seed-0001', 'run-4').status).toBe('stopped')
    expect(listDelegatedRuns('dc-seed-0001').items.find((r) => r.run_id === 'run-4')!.status).toBe('stopped')
  })

  it('stop on a finished run leaves its status unchanged', () => {
    expect(stopDelegatedRun('dc-seed-0001', 'run-3').status).toBe('completed')
  })

  it('throws NotFoundError for an unknown run', () => {
    expect(() => stopDelegatedRun('dc-seed-0001', 'nope')).toThrow(NotFoundError)
  })
})
