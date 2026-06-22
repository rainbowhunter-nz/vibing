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
  const items = store[devcontainerId]
  return items ? { items: items.map((h) => ({ ...h })), known: true } : { items: [], known: false }
}

function find(devcontainerId: string, name: string): HarnessStatus {
  const entry = store[devcontainerId]
  const h = entry?.find((x) => x.name === name)
  if (!h) throw new NotFoundError(name)
  return h
}

// Ensures a harness entry exists for devcontainerId, seeding a default list if absent.
// Called by injectRuntime so the harness panel becomes known after runtime injection.
export function ensureHarnessEntry(devcontainerId: string): void {
  if (!store[devcontainerId]) {
    store[devcontainerId] = [{ name: 'claude-code', installed: false, authenticated: false }]
  }
}

// Mirrors the backend evicting the harness cache when a container is removed.
export function evictHarnessEntry(devcontainerId: string): void {
  delete store[devcontainerId]
}

export function installHarness(devcontainerId: string, name: string): HarnessStatus {
  const h = find(devcontainerId, name)
  h.installed = true
  return { ...h }
}

export function authenticateHarness(devcontainerId: string, name: string): HarnessStatus {
  const h = find(devcontainerId, name)
  h.authenticated = true
  return { ...h }
}
