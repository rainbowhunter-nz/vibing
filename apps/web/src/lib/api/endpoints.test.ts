import { describe, expect, it, vi, beforeEach } from 'vitest'
import { injectRuntime } from './endpoints'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('injectRuntime', () => {
  it('POSTs to inject-runtime', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 202 }))
    await injectRuntime('dc-1')
    expect(spy).toHaveBeenCalledWith(
      '/api/v1/devcontainers/dc-1/inject-runtime',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
