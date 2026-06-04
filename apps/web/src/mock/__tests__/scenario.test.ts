import { describe, it, expect, beforeEach, beforeAll, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { setScenario, resetScenario } from '../scenario'
import { resetDevcontainers } from '../state/devcontainers'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => {
  server.resetHandlers()
  resetScenario()
  resetDevcontainers()
})
afterAll(() => server.close())

async function get(path: string) {
  return fetch(`http://localhost${path}`)
}

describe('scenario switching — handler responses', () => {
  it('happy (default) returns 200 fixture data', async () => {
    const res = await get('/api/v1/health')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toMatchObject({ status: 'ok', service: 'vibing' })
  })

  it('empty — list endpoints return empty items', async () => {
    setScenario('empty')
    const devcontainers = await (await get('/api/v1/devcontainers')).json()
    expect(devcontainers.items).toEqual([])
    const inbox = await (await get('/api/v1/inbox-events')).json()
    expect(inbox.items).toEqual([])
    const approvals = await (await get('/api/v1/approval-requests')).json()
    expect(approvals.items).toEqual([])
  })

  it('api-error — all endpoints return 500 with error envelope', async () => {
    setScenario('api-error')
    for (const path of ['/api/v1/health', '/api/v1/devcontainers', '/api/v1/settings']) {
      const res = await get(path)
      expect(res.status).toBe(500)
      const body = await res.json()
      expect(body.error.code).toBe('INTERNAL_ERROR')
    }
  })

  it('network-down — fetch rejects (network error)', async () => {
    setScenario('network-down')
    await expect(get('/api/v1/health')).rejects.toThrow()
  })

  it('not-found — returns 404 error envelope', async () => {
    setScenario('not-found')
    const res = await get('/api/v1/health')
    expect(res.status).toBe(404)
    const body = await res.json()
    expect(body.error.code).toBe('NOT_FOUND')
  })

  it('stale-action — returns 409 error envelope', async () => {
    setScenario('stale-action')
    const res = await get('/api/v1/health')
    expect(res.status).toBe(409)
    const body = await res.json()
    expect(body.error.code).toBe('CONFLICT')
  })

  it('switching back to happy restores 200 fixture responses', async () => {
    setScenario('api-error')
    expect((await get('/api/v1/health')).status).toBe(500)
    setScenario('happy')
    expect((await get('/api/v1/health')).status).toBe(200)
  })
})
