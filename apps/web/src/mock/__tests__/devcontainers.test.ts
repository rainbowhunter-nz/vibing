import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { setScenario, resetScenario } from '../scenario'
import { resetDevcontainers } from '../state/devcontainers'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetDevcontainers() })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

async function get(path: string) {
  return fetch(`http://localhost${path}`)
}

async function post(path: string, body?: unknown) {
  return fetch(`http://localhost${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

async function patch(path: string, body: unknown) {
  return fetch(`http://localhost${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

async function del(path: string) {
  return fetch(`http://localhost${path}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// List — GET /api/v1/devcontainers
// ---------------------------------------------------------------------------

describe('GET /api/v1/devcontainers', () => {
  it('happy — returns seeded items (populated)', async () => {
    const res = await get('/api/v1/devcontainers')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items.length).toBeGreaterThanOrEqual(4)
    expect(body.items[0]).toMatchObject({ id: 'dc-seed-0001', status: 'running' })
  })

  it('empty scenario — returns empty list', async () => {
    setScenario('empty')
    const res = await get('/api/v1/devcontainers')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items).toEqual([])
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await get('/api/v1/devcontainers')
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error.code).toBe('INTERNAL_ERROR')
  })

  it('network-down scenario — fetch rejects', async () => {
    setScenario('network-down')
    await expect(get('/api/v1/devcontainers')).rejects.toThrow()
  })
})

// ---------------------------------------------------------------------------
// Detail — GET /api/v1/devcontainers/:id
// ---------------------------------------------------------------------------

describe('GET /api/v1/devcontainers/:id', () => {
  it('happy — returns 200 for seeded id', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.id).toBe('dc-seed-0001')
    expect(body.name).toBe('my-webapp')
  })

  it('happy — returns 404 DEVCONTAINER_NOT_FOUND for unknown id', async () => {
    const res = await get('/api/v1/devcontainers/nonexistent')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })

  it('not-found scenario — returns 404 DEVCONTAINER_NOT_FOUND for any id', async () => {
    setScenario('not-found')
    const res = await get('/api/v1/devcontainers/dc-seed-0001')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await get('/api/v1/devcontainers/dc-seed-0001')
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error.code).toBe('INTERNAL_ERROR')
  })
})

// ---------------------------------------------------------------------------
// Agent sessions — GET /api/v1/devcontainers/:id/agent-sessions
// ---------------------------------------------------------------------------

describe('GET /api/v1/devcontainers/:id/agent-sessions', () => {
  it('happy — returns only the requesting devcontainer’s sessions', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items).toHaveLength(4)
    expect(body.items.every((s: { devcontainer_id: string }) => s.devcontainer_id === 'dc-seed-0001')).toBe(true)
  })

  it('happy — returns empty items for a seeded id with no sessions', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0003/agent-sessions')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items).toEqual([])
  })

  it('happy — returns 404 for unknown devcontainer id', async () => {
    const res = await get('/api/v1/devcontainers/nope/agent-sessions')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })
})

// ---------------------------------------------------------------------------
// Create — POST /api/v1/devcontainers
// ---------------------------------------------------------------------------

describe('POST /api/v1/devcontainers', () => {
  it('happy — creates a devcontainer and refetch reflects it', async () => {
    const res = await post('/api/v1/devcontainers', { name: 'new-dc', local_path: '/tmp/new-dc' })
    expect(res.status).toBe(201)
    const created = await res.json()
    expect(created.name).toBe('new-dc')
    expect(created.status).toBe('created')

    const list = await (await get('/api/v1/devcontainers')).json()
    expect(list.items.some((d: { id: string }) => d.id === created.id)).toBe(true)
  })

  it('api-error scenario — returns 500 (action-failure)', async () => {
    setScenario('api-error')
    const res = await post('/api/v1/devcontainers', { name: 'x', local_path: '/tmp/x' })
    expect(res.status).toBe(500)
  })

  it('stale-action scenario — returns 409 (action-failure)', async () => {
    setScenario('stale-action')
    const res = await post('/api/v1/devcontainers', { name: 'x', local_path: '/tmp/x' })
    expect(res.status).toBe(409)
    const body = await res.json()
    expect(body.error.code).toBe('CONFLICT')
  })
})

// ---------------------------------------------------------------------------
// Start — POST /api/v1/devcontainers/:id/start
// ---------------------------------------------------------------------------

describe('POST /api/v1/devcontainers/:id/start', () => {
  it('happy — sets status to running; subsequent GET reflects change', async () => {
    const res = await post('/api/v1/devcontainers/dc-seed-0002/start')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.status).toBe('running')

    const detail = await (await get('/api/v1/devcontainers/dc-seed-0002')).json()
    expect(detail.status).toBe('running')
  })

  it('api-error scenario — returns 500 (action-failure)', async () => {
    setScenario('api-error')
    const res = await post('/api/v1/devcontainers/dc-seed-0002/start')
    expect(res.status).toBe(500)
  })

  it('stale-action scenario — returns 409 (action-failure)', async () => {
    setScenario('stale-action')
    const res = await post('/api/v1/devcontainers/dc-seed-0002/start')
    expect(res.status).toBe(409)
  })

  it('unknown id — returns 404 DEVCONTAINER_NOT_FOUND', async () => {
    const res = await post('/api/v1/devcontainers/nope/start')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })
})

// ---------------------------------------------------------------------------
// Stop — POST /api/v1/devcontainers/:id/stop
// ---------------------------------------------------------------------------

describe('POST /api/v1/devcontainers/:id/stop', () => {
  it('happy — sets status to stopped; subsequent GET reflects change', async () => {
    const res = await post('/api/v1/devcontainers/dc-seed-0001/stop')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.status).toBe('stopped')

    const detail = await (await get('/api/v1/devcontainers/dc-seed-0001')).json()
    expect(detail.status).toBe('stopped')
  })

  it('api-error scenario — returns 500 (action-failure)', async () => {
    setScenario('api-error')
    const res = await post('/api/v1/devcontainers/dc-seed-0001/stop')
    expect(res.status).toBe(500)
  })

  it('unknown id — returns 404 DEVCONTAINER_NOT_FOUND', async () => {
    const res = await post('/api/v1/devcontainers/nope/stop')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })
})

// ---------------------------------------------------------------------------
// Edit — PATCH /api/v1/devcontainers/:id
// ---------------------------------------------------------------------------

describe('PATCH /api/v1/devcontainers/:id', () => {
  it('happy — renames and GET reflects the new name', async () => {
    const res = await patch('/api/v1/devcontainers/dc-seed-0002', { name: 'renamed' })
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.name).toBe('renamed')

    const detail = await (await get('/api/v1/devcontainers/dc-seed-0002')).json()
    expect(detail.name).toBe('renamed')
  })

  it('unknown id — returns 404 DEVCONTAINER_NOT_FOUND', async () => {
    const res = await patch('/api/v1/devcontainers/nope', { name: 'x' })
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })
})

// ---------------------------------------------------------------------------
// Delete — DELETE /api/v1/devcontainers/:id
// ---------------------------------------------------------------------------

describe('DELETE /api/v1/devcontainers/:id', () => {
  it('happy — 204 and GET list no longer includes the item', async () => {
    const res = await del('/api/v1/devcontainers/dc-seed-0003')
    expect(res.status).toBe(204)

    const list = await (await get('/api/v1/devcontainers')).json()
    expect(list.items.find((d: { id: string }) => d.id === 'dc-seed-0003')).toBeUndefined()
  })

  it('api-error scenario — returns 500 (action-failure)', async () => {
    setScenario('api-error')
    const res = await del('/api/v1/devcontainers/dc-seed-0003')
    expect(res.status).toBe(500)
  })

  it('stale-action scenario — returns 409 (action-failure)', async () => {
    setScenario('stale-action')
    const res = await del('/api/v1/devcontainers/dc-seed-0003')
    expect(res.status).toBe(409)
  })

  it('unknown id — returns 404 DEVCONTAINER_NOT_FOUND', async () => {
    const res = await del('/api/v1/devcontainers/nope')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })
})

// ---------------------------------------------------------------------------
// Mutation persistence — start mutates so list refetch shows it
// ---------------------------------------------------------------------------

describe('mutation persistence across requests', () => {
  it('start → list shows running status', async () => {
    await post('/api/v1/devcontainers/dc-seed-0002/start')
    const list = await (await get('/api/v1/devcontainers')).json()
    const dc = list.items.find((d: { id: string }) => d.id === 'dc-seed-0002')
    expect(dc?.status).toBe('running')
  })

  it('create → list includes new item', async () => {
    const { id } = await (await post('/api/v1/devcontainers', { name: 'added', local_path: '/tmp/added' })).json()
    const list = await (await get('/api/v1/devcontainers')).json()
    expect(list.items.some((d: { id: string }) => d.id === id)).toBe(true)
  })

  it('delete → GET detail returns 404', async () => {
    await del('/api/v1/devcontainers/dc-seed-0004')
    const res = await get('/api/v1/devcontainers/dc-seed-0004')
    expect(res.status).toBe(404)
  })
})
