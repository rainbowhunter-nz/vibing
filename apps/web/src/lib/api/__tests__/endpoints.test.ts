import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createDevcontainer,
  deleteDevcontainer,
  fetchDevcontainer,
  startDevcontainer,
  stopDevcontainer,
  updateDevcontainer,
} from '../endpoints'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const devcontainer = {
  id: 'abc',
  name: 'my-env',
  local_path: '/home/user/proj',
  status: 'created',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

afterEach(() => vi.unstubAllGlobals())

describe('createDevcontainer', () => {
  it('POSTs to /devcontainers with name and local_path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, devcontainer))
    vi.stubGlobal('fetch', fetchMock)
    const result = await createDevcontainer({ name: 'my-env', local_path: '/home/user/proj' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).body).toBe(JSON.stringify({ name: 'my-env', local_path: '/home/user/proj' }))
    expect(result).toEqual(devcontainer)
  })
})

describe('fetchDevcontainer', () => {
  it('GETs /devcontainers/{id} with encoded id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, devcontainer))
    vi.stubGlobal('fetch', fetchMock)
    const result = await fetchDevcontainer('a b/c')
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/a%20b%2Fc')
    expect(result).toEqual(devcontainer)
  })
})

describe('updateDevcontainer', () => {
  it('PATCHes /devcontainers/{id} with partial body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ...devcontainer, name: 'renamed' }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await updateDevcontainer('abc', { name: 'renamed' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/abc')
    expect((init as RequestInit).method).toBe('PATCH')
    expect((init as RequestInit).body).toBe(JSON.stringify({ name: 'renamed' }))
    expect(result).toEqual({ ...devcontainer, name: 'renamed' })
  })

  it('PATCHes with status field', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ...devcontainer, status: 'stopped' }))
    vi.stubGlobal('fetch', fetchMock)
    await updateDevcontainer('abc', { status: 'stopped' })
    const [, init] = fetchMock.mock.calls[0]
    expect((init as RequestInit).body).toBe(JSON.stringify({ status: 'stopped' }))
  })
})

describe('deleteDevcontainer', () => {
  it('DELETEs /devcontainers/{id} and returns undefined on 204', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await deleteDevcontainer('abc')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/abc')
    expect((init as RequestInit).method).toBe('DELETE')
    expect(result).toBeUndefined()
  })

  it('encodes special characters in id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    await deleteDevcontainer('a/b c')
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/a%2Fb%20c')
  })
})

describe('startDevcontainer', () => {
  it('POSTs to /devcontainers/{id}/start with no body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, { ...devcontainer, status: 'starting' }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await startDevcontainer('abc')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/abc/start')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).body).toBeUndefined()
    expect(result).toEqual({ ...devcontainer, status: 'starting' })
  })
})

describe('stopDevcontainer', () => {
  it('POSTs to /devcontainers/{id}/stop with no body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, { ...devcontainer, status: 'stopping' }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await stopDevcontainer('abc')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/abc/stop')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).body).toBeUndefined()
    expect(result).toEqual({ ...devcontainer, status: 'stopping' })
  })
})
