import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { setScenario, resetScenario } from '../scenario'
import { resetDevcontainers } from '../state/devcontainers'
import { resetAgentSessions } from '../state/agentSessions'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetDevcontainers(); resetAgentSessions() })
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

async function del(path: string) {
  return fetch(`http://localhost${path}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// GET /api/v1/devcontainers/:id — returns DevcontainerView with runtime
// ---------------------------------------------------------------------------

describe('GET /api/v1/devcontainers/:id — runtime field', () => {
  it('returns runtime connection info for seeded devcontainer', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.runtime).toEqual({ worker_connected: true, agent_connected: true })
  })

  it('dc-seed-0002 has runtime with agent_connected: false', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0002')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.runtime).toEqual({ worker_connected: false, agent_connected: false })
  })
})

// ---------------------------------------------------------------------------
// GET /api/v1/devcontainers/:id/agent-sessions — reads mutable store
// ---------------------------------------------------------------------------

describe('GET /api/v1/devcontainers/:id/agent-sessions', () => {
  it('happy — returns only sessions for the given devcontainer', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items.length).toBeGreaterThanOrEqual(1)
    expect(body.items.every((s: { devcontainer_id: string }) => s.devcontainer_id === 'dc-seed-0001')).toBe(true)
  })

  it('happy — empty for devcontainer with no sessions', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0003/agent-sessions')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items).toEqual([])
  })

  it('returns 404 for unknown devcontainer', async () => {
    const res = await get('/api/v1/devcontainers/nope/agent-sessions')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })
})

// ---------------------------------------------------------------------------
// GET /api/v1/devcontainers/:dc/agent-sessions/:sid — detail
describe('GET /api/v1/devcontainers/:dc/agent-sessions/:sid', () => {
  it('returns session with summary_text for completed seed session', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0004')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.id).toBe('as-seed-0004')
    expect(body.prompt).toBe('Fix the flaky test in auth')
    expect(body.summary_text).toBe('All tests passed. Ready to merge.')
  })

  it('returns 404 for unknown session', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions/nope')
    expect(res.status).toBe(404)
    expect((await res.json()).error.code).toBe('AGENT_SESSION_NOT_FOUND')
  })
})

// POST /api/v1/devcontainers/:id/agent-sessions — start
// ---------------------------------------------------------------------------

describe('POST /api/v1/devcontainers/:id/agent-sessions (start)', () => {
  it('happy — creates a session with status starting; subsequent GET reflects it', async () => {
    const res = await post('/api/v1/devcontainers/dc-seed-0003/agent-sessions', { prompt: 'do something' })
    expect(res.status).toBe(201)
    const session = await res.json()
    expect(session.devcontainer_id).toBe('dc-seed-0003')
    expect(session.status).toBe('starting')
    expect(session.id).toMatch(/^as-mock-/)

    const list = await (await get('/api/v1/devcontainers/dc-seed-0003/agent-sessions')).json()
    expect(list.items.some((s: { id: string }) => s.id === session.id)).toBe(true)
  })

  it('returns 404 for unknown devcontainer', async () => {
    const res = await post('/api/v1/devcontainers/nope/agent-sessions', { prompt: 'x' })
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await post('/api/v1/devcontainers/dc-seed-0003/agent-sessions', { prompt: 'x' })
    expect(res.status).toBe(500)
  })

  it('stale-action scenario — returns 409', async () => {
    setScenario('stale-action')
    const res = await post('/api/v1/devcontainers/dc-seed-0003/agent-sessions', { prompt: 'x' })
    expect(res.status).toBe(409)
  })
})

// ---------------------------------------------------------------------------
// POST /api/v1/devcontainers/:dc/agent-sessions/:sid/stop
// ---------------------------------------------------------------------------

describe('POST /api/v1/devcontainers/:dc/agent-sessions/:sid/stop', () => {
  it('happy — updates session status to stopped; subsequent GET reflects it', async () => {
    const res = await post('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0001/stop')
    expect(res.status).toBe(200)
    const session = await res.json()
    expect(session.status).toBe('stopped')
    expect(session.ended_at).not.toBeNull()

    const list = await (await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions')).json()
    const updated = list.items.find((s: { id: string }) => s.id === 'as-seed-0001')
    expect(updated?.status).toBe('stopped')
  })

  it('returns 404 for unknown session', async () => {
    const res = await post('/api/v1/devcontainers/dc-seed-0001/agent-sessions/nope/stop')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('AGENT_SESSION_NOT_FOUND')
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await post('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0001/stop')
    expect(res.status).toBe(500)
  })
})

// ---------------------------------------------------------------------------
// Mutation persistence
// ---------------------------------------------------------------------------

describe('agent session mutation persistence', () => {
  it('start → GET list includes new session', async () => {
    const { id } = await (await post('/api/v1/devcontainers/dc-seed-0003/agent-sessions', { prompt: 'task' })).json()
    const list = await (await get('/api/v1/devcontainers/dc-seed-0003/agent-sessions')).json()
    expect(list.items.some((s: { id: string }) => s.id === id)).toBe(true)
  })

  it('stop → GET list shows stopped status', async () => {
    await post('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0005/stop')
    const list = await (await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions')).json()
    const session = list.items.find((s: { id: string }) => s.id === 'as-seed-0005')
    expect(session?.status).toBe('stopped')
  })
})

// ---------------------------------------------------------------------------
// DELETE /api/v1/devcontainers/:dc/agent-sessions/:sid
// ---------------------------------------------------------------------------

describe('DELETE /api/v1/devcontainers/:dc/agent-sessions/:sid', () => {
  it('happy — removes non-active session from list', async () => {
    const res = await del('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0004')
    expect(res.status).toBe(204)

    const list = await (await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions')).json()
    expect(list.items.some((s: { id: string }) => s.id === 'as-seed-0004')).toBe(false)
  })

  it('returns 409 for active session', async () => {
    const res = await del('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0005')
    expect(res.status).toBe(409)
    const body = await res.json()
    expect(body.error.code).toBe('AGENT_SESSION_STILL_ACTIVE')
  })

  it('returns 404 for unknown session', async () => {
    const res = await del('/api/v1/devcontainers/dc-seed-0001/agent-sessions/nope')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('AGENT_SESSION_NOT_FOUND')
  })
})
