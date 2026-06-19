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

describe('harness + delegated-run handlers', () => {
  it('GET /harnesses returns seeded list', async () => {
    const body = await (await get('/api/v1/devcontainers/dc-seed-0001/harnesses')).json()
    expect(body.items.map((h: { name: string }) => h.name)).toContain('codex')
  })

  it('GET /harnesses 404s for unknown devcontainer', async () => {
    const res = await get('/api/v1/devcontainers/nope/harnesses')
    expect(res.status).toBe(404)
    expect((await res.json()).error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })

  it('POST install flips installed and refetch reflects it', async () => {
    expect((await (await post('/api/v1/devcontainers/dc-seed-0001/harnesses/cursor/install')).json()).installed).toBe(true)
    const list = await (await get('/api/v1/devcontainers/dc-seed-0001/harnesses')).json()
    expect(list.items.find((h: { name: string }) => h.name === 'cursor').installed).toBe(true)
  })

  it('POST authenticate flips authenticated', async () => {
    expect((await (await post('/api/v1/devcontainers/dc-seed-0001/harnesses/codex/authenticate')).json()).authenticated).toBe(true)
  })

  it('GET /delegated-runs returns seeded runs', async () => {
    const body = await (await get('/api/v1/devcontainers/dc-seed-0001/delegated-runs')).json()
    expect(body.items.map((r: { run_id: string }) => r.run_id)).toEqual(['run-4', 'run-3', 'run-2'])
  })

  it('POST stop flips a running run to stopped', async () => {
    const body = await (await post('/api/v1/devcontainers/dc-seed-0001/delegated-runs/run-4/stop')).json()
    expect(body.status).toBe('stopped')
  })
})
