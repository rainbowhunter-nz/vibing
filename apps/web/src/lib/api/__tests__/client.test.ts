import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError, getJson, sendJson } from '../client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('getJson', () => {
  it('resolves parsed body on 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, { status: 'ok', service: 'vibing-api' })),
    )
    await expect(getJson('/health')).resolves.toEqual({
      status: 'ok',
      service: 'vibing-api',
    })
  })

  it('prepends /api/v1 and sends Accept: application/json', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    await getJson('/workspaces')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/workspaces')
    expect((init as RequestInit).headers).toEqual({ Accept: 'application/json' })
  })

  it('throws ApiError parsed from envelope on 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(404, {
          error: { code: 'WORKSPACE_NOT_FOUND', message: 'Workspace not found: x', details: null },
        }),
      ),
    )
    await expect(getJson('/workspaces/x')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      code: 'WORKSPACE_NOT_FOUND',
      message: 'Workspace not found: x',
      details: null,
    })
  })

  it('preserves envelope details on 422', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(422, {
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Request validation failed',
            details: [{ loc: ['body', 'name'], msg: 'field required' }],
          },
        }),
      ),
    )
    await expect(getJson('/workspaces')).rejects.toMatchObject({
      status: 422,
      code: 'VALIDATION_ERROR',
      details: [{ loc: ['body', 'name'], msg: 'field required' }],
    })
  })

  it('falls back to ApiError(HTTP_ERROR) when body is not the envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('<html>nope</html>', {
          status: 500,
          statusText: 'Internal Server Error',
        }),
      ),
    )
    await expect(getJson('/anything')).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
      code: 'HTTP_ERROR',
    })
  })

  it('throws NetworkError when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))
    await expect(getJson('/health')).rejects.toMatchObject({
      name: 'NetworkError',
      message: 'network down',
    })
  })

  it('returns an ApiError instance (not a plain Error)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(404, { error: { code: 'X', message: 'y', details: null } }),
      ),
    )
    await expect(getJson('/x')).rejects.toBeInstanceOf(ApiError)
  })

  it('returns a NetworkError instance', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('dead')))
    await expect(getJson('/x')).rejects.toBeInstanceOf(NetworkError)
  })
})

describe('sendJson', () => {
  it('sends method, Content-Type, and serialized body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    await sendJson('/workspaces', 'POST', { name: 'a', local_path: '/tmp' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/workspaces')
    const reqInit = init as RequestInit
    expect(reqInit.method).toBe('POST')
    expect(reqInit.body).toBe(JSON.stringify({ name: 'a', local_path: '/tmp' }))
    expect(reqInit.headers).toEqual({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    })
  })

  it('resolves undefined on 204', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('', { status: 204 })),
    )
    await expect(sendJson('/workspaces/x', 'DELETE')).resolves.toBeUndefined()
  })

  it('omits Content-Type when no body is provided', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    await sendJson('/workspaces/x', 'DELETE')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.headers).toEqual({ Accept: 'application/json' })
    expect(init.body).toBeUndefined()
  })

  it('throws ApiError on non-2xx envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(404, { error: { code: 'WORKSPACE_NOT_FOUND', message: 'gone', details: null } }),
      ),
    )
    await expect(sendJson('/workspaces/x', 'DELETE')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      code: 'WORKSPACE_NOT_FOUND',
    })
  })
})
