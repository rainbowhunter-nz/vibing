import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { resetScenario } from '../scenario'
import { resetDevcontainers } from '../state/devcontainers'
import { resetInbox } from '../state/inbox'
import { resetApprovals } from '../state/approvals'
import * as f from '../fixtures'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetDevcontainers(); resetInbox(); resetApprovals() })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

async function get(path: string) {
  const res = await fetch(`http://localhost${path}`)
  return res.json()
}

describe('mock handlers — healthy baseline', () => {
  it('GET /api/v1/health', async () => {
    expect(await get('/api/v1/health')).toEqual(f.health)
  })

  it('GET /api/v1/status', async () => {
    expect(await get('/api/v1/status')).toEqual(f.status)
  })

  it('GET /api/v1/config', async () => {
    expect(await get('/api/v1/config')).toEqual(f.config)
  })

  it('GET /api/v1/runtime/status', async () => {
    expect(await get('/api/v1/runtime/status')).toEqual(f.runtimeStatus)
  })

  it('GET /api/v1/settings', async () => {
    expect(await get('/api/v1/settings')).toEqual(f.settings)
  })

  it('GET /api/v1/diagnostics', async () => {
    expect(await get('/api/v1/diagnostics')).toEqual(f.diagnostics)
  })

  // devcontainers now returns the seeded store under happy (populated, not empty).
  it('GET /api/v1/devcontainers — happy returns seeded items', async () => {
    const body = await get('/api/v1/devcontainers')
    expect(body.items.length).toBeGreaterThanOrEqual(4)
    expect(body.items[0]).toMatchObject({ id: 'dc-seed-0001', name: 'my-webapp', status: 'running' })
  })

  // inbox now returns the seeded store under happy (populated, not empty).
  it('GET /api/v1/inbox-events — happy returns seeded items', async () => {
    const body = await get('/api/v1/inbox-events')
    expect(body.items.length).toBe(4)
    const types = body.items.map((e: { event_type: string }) => e.event_type)
    expect(types).toContain('question')
    expect(types).toContain('approval_request')
    expect(types).toContain('failure')
    expect(types).toContain('completion')
  })

  it('GET /api/v1/approval-requests — happy returns seeded items', async () => {
    const body = await get('/api/v1/approval-requests')
    expect(body.items.length).toBeGreaterThanOrEqual(3)
    const statuses = body.items.map((r: { status: string }) => r.status)
    expect(statuses).toContain('pending')
    expect(statuses).toContain('approved')
    expect(statuses).toContain('rejected')
  })
})
