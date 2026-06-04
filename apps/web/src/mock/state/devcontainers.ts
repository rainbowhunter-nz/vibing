import type { Devcontainer, DevcontainerCreateBody, DevcontainerUpdateBody, DevcontainerView, DevcontainerViewList, RuntimeConnection } from '../../lib/api/types'
import { seedDevcontainers } from './seeds'

// Runtime connection per seed devcontainer; my-webapp is fully connected for inspection.
const SEED_RUNTIME: Record<string, RuntimeConnection> = {
  'dc-seed-0001': { worker_connected: true, agent_connected: true },
  'dc-seed-0002': { worker_connected: false, agent_connected: false },
  'dc-seed-0003': { worker_connected: false, agent_connected: false },
  'dc-seed-0004': { worker_connected: false, agent_connected: false },
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

export function getDevcontainer(id: string): Devcontainer {
  return toDevcontainer(store[findIdx(id)])
}

export function createDevcontainer(body: DevcontainerCreateBody): Devcontainer {
  const ts = now()
  const view: DevcontainerView = {
    id: `dc-mock-${String(nextIdSeq++).padStart(4, '0')}`,
    name: body.name,
    local_path: body.local_path,
    status: 'created',
    created_at: ts,
    updated_at: ts,
    runtime: { worker_connected: false, agent_connected: false },
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

export function stopDevcontainer(id: string): Devcontainer {
  const idx = findIdx(id)
  store[idx] = { ...store[idx], status: 'stopped', updated_at: now() }
  return toDevcontainer(store[idx])
}

export function deleteDevcontainer(id: string): void {
  const idx = findIdx(id)
  store.splice(idx, 1)
}
