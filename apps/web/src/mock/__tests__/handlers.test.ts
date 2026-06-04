import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { resetScenario } from '../scenario'
import * as f from '../fixtures'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => resetScenario())
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

  it('GET /api/v1/devcontainers', async () => {
    expect(await get('/api/v1/devcontainers')).toEqual(f.devcontainers)
  })

  it('GET /api/v1/inbox-events', async () => {
    expect(await get('/api/v1/inbox-events')).toEqual(f.inboxEvents)
  })

  it('GET /api/v1/approval-requests', async () => {
    expect(await get('/api/v1/approval-requests')).toEqual(f.approvalRequests)
  })
})
