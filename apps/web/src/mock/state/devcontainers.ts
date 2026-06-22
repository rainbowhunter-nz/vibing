import type { Devcontainer, DevcontainerCreateBody, DevcontainerUpdateBody, DevcontainerView, DevcontainerViewList, RuntimeConnection } from '../../lib/api/types'
import { seedDevcontainers } from './seeds'
import { ensureHarnessEntry, evictHarnessEntry } from './harnesses'

// Runtime connection per seed devcontainer; my-webapp is connected for inspection.
const SEED_RUNTIME: Record<string, RuntimeConnection> = {
  'dc-seed-0001': { state: 'connected' },
  'dc-seed-0002': { state: 'disconnected' },
  'dc-seed-0003': { state: 'disconnected' },
  'dc-seed-0004': { state: 'disconnected' },
}

const SEED: DevcontainerView[] = seedDevcontainers.map((d) => ({ ...d, runtime: SEED_RUNTIME[d.id] }))

let store: DevcontainerView[] = SEED.map((d) => ({ ...d }))
let nextIdSeq = 100

function now(): string {
  return new Date().toISOString()
}

function toDevcontainer(view: DevcontainerView): Devcontainer {
  return {
    id: view.id,
    name: view.name,
    local_path: view.local_path,
    status: view.status,
    source: view.source,
    created_at: view.created_at,
    updated_at: view.updated_at,
  }
}

function findIdx(id: string): number {
  const idx = store.findIndex((d) => d.id === id)
  if (idx === -1) throw new NotFoundError(id)
  return idx
}

export class NotFoundError extends Error {
  readonly code = 'DEVCONTAINER_NOT_FOUND'
  constructor(id: string) {
    super(`Devcontainer not found: ${id}`)
  }
}

export function resetDevcontainers(): void {
  store = SEED.map((d) => ({ ...d }))
  nextIdSeq = 100
}

export function listDevcontainers(): DevcontainerViewList {
  return { items: store.map((d) => ({ ...d })) }
}

export function getDevcontainer(id: string): DevcontainerView {
  return { ...store[findIdx(id)] }
}

export function createDevcontainer(body: DevcontainerCreateBody): Devcontainer {
  const ts = now()
  const view: DevcontainerView = {
    id: `dc-mock-${String(nextIdSeq++).padStart(4, '0')}`,
    name: body.name,
    local_path: body.local_path,
    status: 'stopped',
    source: 'manual',
    created_at: ts,
    updated_at: ts,
    runtime: { state: 'disconnected' },
  }
  store.push(view)
  return toDevcontainer(view)
}

export function updateDevcontainer(id: string, body: DevcontainerUpdateBody): Devcontainer {
  const idx = findIdx(id)
  store[idx] = { ...store[idx], ...body, updated_at: now() }
  return toDevcontainer(store[idx])
}

export function startDevcontainer(id: string): Devcontainer {
  const idx = findIdx(id)
  store[idx] = { ...store[idx], status: 'running', updated_at: now() }
  return toDevcontainer(store[idx])
}

// Stopping the container tears down the runtime: disconnect it and evict the
// harness cache so runtime-dependent status reverts to unknown.
export function stopDevcontainer(id: string): Devcontainer {
  const idx = findIdx(id)
  store[idx] = {
    ...store[idx],
    status: 'stopped',
    runtime: { state: 'disconnected' },
    updated_at: now(),
  }
  evictHarnessEntry(id)
  return toDevcontainer(store[idx])
}

// Kill+remove the container but keep the record: status back to stopped,
// runtime disconnected, harness cache evicted (mirrors backend remove-container).
export function removeContainer(id: string): void {
  const idx = findIdx(id)
  store[idx] = {
    ...store[idx],
    status: 'stopped',
    runtime: { state: 'disconnected' },
    updated_at: now(),
  }
  evictHarnessEntry(id)
}

export function deleteDevcontainer(id: string): void {
  const dc = store.find((d) => d.id === id)
  if (!dc) throw new NotFoundError(id)
  if (dc.source === 'discovered') {
    dc.status = 'stopped'
    return
  }
  store = store.filter((d) => d.id !== id)
}

// Mock divergence: the real backend returns 202 and injects in the background, so the
// runtime connects (and harness status becomes known) only later via the runtime WS/SSE.
// The mock flips synchronously so the reactive UI path (invalidation -> refetch) is testable.
export function injectRuntime(id: string): void {
  const idx = findIdx(id)
  store[idx] = { ...store[idx], runtime: { state: 'connected' }, updated_at: now() }
  ensureHarnessEntry(id)
}

// Stop the runtime: disconnect it and evict harness cache (mirrors backend stop-runtime).
export function stopRuntimeState(id: string): void {
  const idx = findIdx(id)
  store[idx] = { ...store[idx], runtime: { state: 'disconnected' }, updated_at: now() }
  evictHarnessEntry(id)
}
