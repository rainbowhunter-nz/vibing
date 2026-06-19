import type { DelegatedRun, DelegatedRunList } from '../../lib/api/types'
import { seedDelegatedRuns } from './seeds'

export class NotFoundError extends Error {
  readonly code = 'DELEGATED_RUN_NOT_FOUND'
  constructor(runId: string) {
    super(`Delegated run not found: ${runId}`)
  }
}

function clone(src: Record<string, DelegatedRun[]>): Record<string, DelegatedRun[]> {
  return Object.fromEntries(Object.entries(src).map(([k, v]) => [k, v.map((r) => ({ ...r }))]))
}

let store: Record<string, DelegatedRun[]> = clone(seedDelegatedRuns)

export function resetDelegatedRuns(): void {
  store = clone(seedDelegatedRuns)
}

export function listDelegatedRuns(devcontainerId: string): DelegatedRunList {
  return { items: (store[devcontainerId] ?? []).map((r) => ({ ...r })) }
}

export function stopDelegatedRun(devcontainerId: string, runId: string): DelegatedRun {
  const r = (store[devcontainerId] ?? []).find((x) => x.run_id === runId)
  if (!r) throw new NotFoundError(runId)
  if (r.status === 'running') r.status = 'stopped'
  return { ...r }
}
