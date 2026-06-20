import type { DelegatedRun, DelegatedRunList } from '../../lib/api/types'
import { seedDelegatedRuns } from './seeds'

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
