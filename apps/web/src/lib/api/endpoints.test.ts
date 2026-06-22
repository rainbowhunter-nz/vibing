import { describe, expect, it, vi, beforeEach } from 'vitest'
import { injectRuntime, removeContainer } from './endpoints'

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

describe('removeContainer', () => {
  it('POSTs to remove-container', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(null, { status: 204 }))
    await removeContainer('dc-1')
    expect(spy).toHaveBeenCalledWith(
      '/api/v1/devcontainers/dc-1/remove-container',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
