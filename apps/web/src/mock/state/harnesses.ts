import type { HarnessStatus, HarnessStatusList } from '../../lib/api/types'
import { seedHarnesses } from './seeds'

export class NotFoundError extends Error {
  readonly code = 'HARNESS_NOT_FOUND'
  constructor(name: string) {
    super(`Harness not found: ${name}`)
  }
}

function clone(src: Record<string, HarnessStatus[]>): Record<string, HarnessStatus[]> {
  return Object.fromEntries(Object.entries(src).map(([k, v]) => [k, v.map((h) => ({ ...h }))]))
}

let store: Record<string, HarnessStatus[]> = clone(seedHarnesses)

export function resetHarnesses(): void {
  store = clone(seedHarnesses)
}

export function listHarnesses(devcontainerId: string): HarnessStatusList {
  return { items: (store[devcontainerId] ?? []).map((h) => ({ ...h })) }
}

function find(devcontainerId: string, name: string): HarnessStatus {
  const h = (store[devcontainerId] ?? []).find((x) => x.name === name)
  if (!h) throw new NotFoundError(name)
  return h
}

export function authenticateHarness(devcontainerId: string, name: string): HarnessStatus {
  const h = find(devcontainerId, name)
  h.authenticated = true
  return { ...h }
}
