import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { setScenario, resetScenario } from '../scenario'
import { resetDevcontainers } from '../state/devcontainers'
import { resetAgentSessions, getAgentSessionTranscript } from '../state/agentSessions'

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

// ---------------------------------------------------------------------------
// getAgentSessionTranscript — store unit tests
// ---------------------------------------------------------------------------

describe('getAgentSessionTranscript — store', () => {
  beforeEach(() => { resetDevcontainers(); resetAgentSessions() })

  it('has_turns for seeded session on connected dc (dc-seed-0001 agent_connected=true)', () => {
    const result = getAgentSessionTranscript('dc-seed-0001', 'as-seed-0004')
    expect(result.state).toBe('has_turns')
    expect(result.turns.length).toBeGreaterThan(0)
    const toolTurn = result.turns.find((t) => t.blocks.some((b) => b.kind === 'tool_use'))
    expect(toolTurn).toBeTruthy()
    const toolBlock = toolTurn!.blocks.find((b) => b.kind === 'tool_use')!
    if (toolBlock.kind === 'tool_use') {
      expect(toolBlock.name).toBe('Bash')
      expect(toolBlock.summary).toBeTruthy()
    }
  })

  it('summary_fallback when dc is not connected (dc-seed-0002 agent_connected=false)', () => {
    const result = getAgentSessionTranscript('dc-seed-0002', 'as-seed-0002')
    expect(result.state).toBe('summary_fallback')
    expect(result.turns).toEqual([])
  })

  it('empty when dc is connected but no turns seeded', () => {
    const result = getAgentSessionTranscript('dc-seed-0001', 'as-seed-0005')
    expect(result.state).toBe('empty')
    expect(result.turns).toEqual([])
  })

  it('throws NotFoundError for unknown session', () => {
    expect(() => getAgentSessionTranscript('dc-seed-0001', 'nope')).toThrow()
  })

  it('resetAgentSessions restores transcript store', () => {
    // Force empty by checking seeded state first, then reset
    const before = getAgentSessionTranscript('dc-seed-0001', 'as-seed-0004')
    expect(before.state).toBe('has_turns')
    resetAgentSessions()
    const after = getAgentSessionTranscript('dc-seed-0001', 'as-seed-0004')
    expect(after.state).toBe('has_turns')
  })
})

// ---------------------------------------------------------------------------
// GET /api/v1/devcontainers/:dc/agent-sessions/:sid/transcript — handler
// ---------------------------------------------------------------------------

describe('GET /api/v1/devcontainers/:dc/agent-sessions/:sid/transcript', () => {
  it('happy — returns has_turns for seeded session on connected dc', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0004/transcript')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.state).toBe('has_turns')
    expect(Array.isArray(body.turns)).toBe(true)
    expect(body.turns.length).toBeGreaterThan(0)
    const hasToolUse = body.turns.some((t: { blocks: { kind: string }[] }) =>
      t.blocks.some((b) => b.kind === 'tool_use'),
    )
    expect(hasToolUse).toBe(true)
  })

  it('happy — returns summary_fallback when dc is stopped (dc-seed-0002)', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0002/agent-sessions/as-seed-0002/transcript')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.state).toBe('summary_fallback')
  })

  it('happy — returns empty for session with no seeded turns', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0005/transcript')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.state).toBe('empty')
  })

  it('returns 404 for unknown session', async () => {
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions/nope/transcript')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('AGENT_SESSION_NOT_FOUND')
  })

  it('returns 404 for unknown devcontainer', async () => {
    const res = await get('/api/v1/devcontainers/nope/agent-sessions/as-seed-0004/transcript')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0004/transcript')
    expect(res.status).toBe(500)
  })

  it('not-found scenario — returns 404 with a not-found code', async () => {
    setScenario('not-found')
    const res = await get('/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0004/transcript')
    expect(res.status).toBe(404)
    const body = await res.json()
    // scenarioFailure uses first arg (DEVCONTAINER_NOT_FOUND) as the not-found code
    expect(['DEVCONTAINER_NOT_FOUND', 'AGENT_SESSION_NOT_FOUND']).toContain(body.error.code)
  })
})
