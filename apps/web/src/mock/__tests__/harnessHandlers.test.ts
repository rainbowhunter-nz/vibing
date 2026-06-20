import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { resetScenario } from '../scenario'
import { resetHarnesses } from '../state/harnesses'
import { resetDelegatedRuns } from '../state/delegatedRuns'

const server = setupServer(...handlers)
beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetHarnesses(); resetDelegatedRuns() })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const get = (p: string) => fetch(`http://localhost${p}`)
const post = (p: string) => fetch(`http://localhost${p}`, { method: 'POST' })

describe('harness handlers', () => {
  it('GET /harnesses returns seeded list', async () => {
    const body = await (await get('/api/v1/devcontainers/dc-seed-0001/harnesses')).json()
    expect(body.items.map((h: { name: string }) => h.name)).toContain('codex')
  })

  it('GET /harnesses 404s for unknown devcontainer', async () => {
    const res = await get('/api/v1/devcontainers/nope/harnesses')
    expect(res.status).toBe(404)
    expect((await res.json()).error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })

  it('POST authenticate flips authenticated', async () => {
    expect((await (await post('/api/v1/devcontainers/dc-seed-0001/harnesses/codex/authenticate')).json()).authenticated).toBe(true)
  })

  it('POST install flips installed', async () => {
    expect((await (await post('/api/v1/devcontainers/dc-seed-0001/harnesses/cursor/install')).json()).installed).toBe(true)
  })
})

describe('delegated-run handlers', () => {
  it('GET /delegated-runs returns seeded runs', async () => {
    const body = await (await get('/api/v1/devcontainers/dc-seed-0001/delegated-runs')).json()
    expect(body.items.map((r: { run_id: string }) => r.run_id)).toEqual(['run-9', 'run-8', 'run-7', 'run-6', 'run-4', 'run-3', 'run-2', 'run-1', 'run-0'])
  })

  it('GET /delegated-runs 404s for unknown devcontainer', async () => {
    const res = await get('/api/v1/devcontainers/nope/delegated-runs')
    expect(res.status).toBe(404)
    expect((await res.json()).error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })
})
