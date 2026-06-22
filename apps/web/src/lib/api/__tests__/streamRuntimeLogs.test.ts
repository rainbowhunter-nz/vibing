import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../../../mock/handlers'
import { resetScenario } from '../../../mock/scenario'
import { resetDevcontainers } from '../../../mock/state/devcontainers'
import { streamRuntimeLogs } from '../endpoints'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetDevcontainers() })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('streamRuntimeLogs', () => {
  it('accumulates chunked content from the stream endpoint', async () => {
    const parts: string[] = []
    await streamRuntimeLogs('dc-seed-0001', new AbortController().signal, (t) => parts.push(t))
    expect(parts.join('')).toContain('runtime started')
  })
})
