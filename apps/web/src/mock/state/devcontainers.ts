import type { Devcontainer, DevcontainerCreateBody, DevcontainerUpdateBody, DevcontainerView, DevcontainerViewList } from '../../lib/api/types'

// Fixed seed data spanning multiple statuses — deterministic for tests.
const SEED: DevcontainerView[] = [
  {
    id: 'dc-seed-0001',
    name: 'my-webapp',
    local_path: '/home/dev/my-webapp',
    status: 'running',
    created_at: '2024-01-10T08:00:00.000Z',
    updated_at: '2024-01-15T10:00:00.000Z',
    runtime: { worker_connected: true, agent_connected: false },
  },
  {
    id: 'dc-seed-0002',
    name: 'api-service',
    local_path: '/home/dev/api-service',
    status: 'stopped',
    created_at: '2024-01-11T09:00:00.000Z',
    updated_at: '2024-01-14T14:30:00.000Z',
    runtime: { worker_connected: false, agent_connected: false },
  },
  {
    id: 'dc-seed-0003',
    name: 'data-pipeline',
    local_path: '/home/dev/data-pipeline',
    status: 'created',
    created_at: '2024-01-12T11:00:00.000Z',
    updated_at: '2024-01-12T11:00:00.000Z',
    runtime: { worker_connected: false, agent_connected: false },
  },
  {
    id: 'dc-seed-0004',
    name: 'legacy-app',
    local_path: '/home/dev/legacy-app',
    status: 'error',
    created_at: '2024-01-08T07:00:00.000Z',
    updated_at: '2024-01-13T16:00:00.000Z',
    runtime: { worker_connected: false, agent_connected: false },
  },
]

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
