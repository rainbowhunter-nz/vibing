import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { resetScenario } from '../scenario'
import { resetDevcontainers } from '../state/devcontainers'
import * as f from '../fixtures'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetDevcontainers() })
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

  it('GET /api/v1/inbox-events', async () => {
    expect(await get('/api/v1/inbox-events')).toEqual(f.inboxEvents)
  })

  it('GET /api/v1/approval-requests', async () => {
    expect(await get('/api/v1/approval-requests')).toEqual(f.approvalRequests)
  })
})
