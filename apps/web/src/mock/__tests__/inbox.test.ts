import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { setScenario, resetScenario } from '../scenario'
import { resetInbox } from '../state/inbox'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetInbox() })
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

// ---------------------------------------------------------------------------
// GET /api/v1/inbox-events (list)
// ---------------------------------------------------------------------------

describe('GET /api/v1/inbox-events', () => {
  it('happy — returns all 4 seeded types', async () => {
    const res = await get('/api/v1/inbox-events')
    expect(res.status).toBe(200)
    const body = await res.json()
    const types = body.items.map((e: { event_type: string }) => e.event_type)
    expect(types).toContain('question')
    expect(types).toContain('approval_request')
    expect(types).toContain('completion')
    expect(types).toContain('failure')
  })

  it('empty scenario — returns empty items', async () => {
    setScenario('empty')
    const res = await get('/api/v1/inbox-events')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items).toEqual([])
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await get('/api/v1/inbox-events')
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error.code).toBe('INTERNAL_ERROR')
  })

  it('network-down scenario — fetch rejects', async () => {
    setScenario('network-down')
    await expect(get('/api/v1/inbox-events')).rejects.toThrow()
  })
})

// ---------------------------------------------------------------------------
// GET /api/v1/inbox-events/:id (detail)
// ---------------------------------------------------------------------------

describe('GET /api/v1/inbox-events/:id', () => {
  it('happy — returns 200 with detail shape for seeded id', async () => {
    const res = await get('/api/v1/inbox-events/ie-seed-0001')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.id).toBe('ie-seed-0001')
    expect(body.event_type).toBe('question')
    expect(body).toHaveProperty('content')
    expect(body).toHaveProperty('devcontainer')
    expect(body.devcontainer).toHaveProperty('name')
    expect(body).toHaveProperty('agent_session')
    expect(body).toHaveProperty('approval_request')
  })

  it('happy — returns 404 INBOX_EVENT_NOT_FOUND for unknown id', async () => {
    const res = await get('/api/v1/inbox-events/nonexistent')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('INBOX_EVENT_NOT_FOUND')
  })

  it('not-found scenario — returns 404 INBOX_EVENT_NOT_FOUND for any id', async () => {
    setScenario('not-found')
    const res = await get('/api/v1/inbox-events/ie-seed-0001')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('INBOX_EVENT_NOT_FOUND')
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await get('/api/v1/inbox-events/ie-seed-0001')
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error.code).toBe('INTERNAL_ERROR')
  })
})

// ---------------------------------------------------------------------------
// POST /api/v1/inbox-events/:id/read
// ---------------------------------------------------------------------------

describe('POST /api/v1/inbox-events/:id/read', () => {
  it('happy — flips unread → read and subsequent GET reflects it', async () => {
    const res = await post('/api/v1/inbox-events/ie-seed-0001/read')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.status).toBe('read')
    expect(body).not.toHaveProperty('content')
    expect(body).not.toHaveProperty('devcontainer')

    const detail = await (await get('/api/v1/inbox-events/ie-seed-0001')).json()
    expect(detail.status).toBe('read')
  })

  it('unknown id — returns 404 INBOX_EVENT_NOT_FOUND', async () => {
    const res = await post('/api/v1/inbox-events/nope/read')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('INBOX_EVENT_NOT_FOUND')
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await post('/api/v1/inbox-events/ie-seed-0001/read')
    expect(res.status).toBe(500)
  })
})

// ---------------------------------------------------------------------------
// POST /api/v1/inbox-events/:id/resolve
// ---------------------------------------------------------------------------

describe('POST /api/v1/inbox-events/:id/resolve', () => {
  it('happy — flips status → resolved and subsequent GET reflects it', async () => {
    const res = await post('/api/v1/inbox-events/ie-seed-0002/resolve')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.status).toBe('resolved')

    const detail = await (await get('/api/v1/inbox-events/ie-seed-0002')).json()
    expect(detail.status).toBe('resolved')
  })

  it('unknown id — returns 404 INBOX_EVENT_NOT_FOUND', async () => {
    const res = await post('/api/v1/inbox-events/nope/resolve')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('INBOX_EVENT_NOT_FOUND')
  })

  it('not-found scenario — returns 404 INBOX_EVENT_NOT_FOUND for any id', async () => {
    setScenario('not-found')
    const res = await post('/api/v1/inbox-events/ie-seed-0002/resolve')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('INBOX_EVENT_NOT_FOUND')
  })
})

// ---------------------------------------------------------------------------
// Agent-session action stubs
// ---------------------------------------------------------------------------

describe('POST /api/v1/devcontainers/:dc/agent-sessions/:sid/user-input', () => {
  it('happy — returns a plausible AgentSession', async () => {
    const res = await post('/api/v1/devcontainers/dc1/agent-sessions/as1/user-input', { inbox_event_id: 'ie1', text: 'ok' })
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.id).toBe('as1')
    expect(body.devcontainer_id).toBe('dc1')
    expect(body).toHaveProperty('status')
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await post('/api/v1/devcontainers/dc1/agent-sessions/as1/user-input', { inbox_event_id: 'ie1', text: 'ok' })
    expect(res.status).toBe(500)
  })
})

describe('POST /api/v1/devcontainers/:dc/agent-sessions/:sid/approval-resolution', () => {
  it('happy — returns a plausible AgentSession', async () => {
    const res = await post('/api/v1/devcontainers/dc1/agent-sessions/as1/approval-resolution', { approval_request_id: 'ar1', resolution: 'approved' })
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.id).toBe('as1')
    expect(body.devcontainer_id).toBe('dc1')
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await post('/api/v1/devcontainers/dc1/agent-sessions/as1/approval-resolution', { approval_request_id: 'ar1', resolution: 'rejected' })
    expect(res.status).toBe(500)
  })
})

// ---------------------------------------------------------------------------
// Completion and failure detail — result/stderr_tail content present (AC6)
// ---------------------------------------------------------------------------

describe('GET /api/v1/inbox-events/:id — completion/failure content', () => {
  it('completion detail carries non-null content', async () => {
    const res = await get('/api/v1/inbox-events/ie-seed-0004')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.event_type).toBe('completion')
    expect(body.content).toBeTruthy()
  })

  it('failure detail carries non-null content', async () => {
    const res = await get('/api/v1/inbox-events/ie-seed-0003')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.event_type).toBe('failure')
    expect(body.content).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Mutation persistence
// ---------------------------------------------------------------------------

describe('mutation persistence', () => {
  it('read → list shows read status', async () => {
    await post('/api/v1/inbox-events/ie-seed-0001/read')
    const list = await (await get('/api/v1/inbox-events')).json()
    const item = list.items.find((e: { id: string }) => e.id === 'ie-seed-0001')
    expect(item?.status).toBe('read')
  })

  it('resolve → detail shows resolved status', async () => {
    await post('/api/v1/inbox-events/ie-seed-0003/resolve')
    const detail = await (await get('/api/v1/inbox-events/ie-seed-0003')).json()
    expect(detail.status).toBe('resolved')
  })
})
