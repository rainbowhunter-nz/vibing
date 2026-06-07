import type { ApiErrorEnvelope } from './types'

export const API_BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NetworkError'
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as ApiErrorEnvelope
    if (body && typeof body.error?.code === 'string' && typeof body.error?.message === 'string') {
      return new ApiError(res.status, body.error.code, body.error.message, body.error.details ?? null)
    }
  } catch {
    // fall through to HTTP_ERROR fallback
  }
  return new ApiError(res.status, 'HTTP_ERROR', res.statusText || `HTTP ${res.status}`)
}

async function callFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${path}`, init)
  } catch (err) {
    throw new NetworkError(err instanceof Error ? err.message : String(err))
  }
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await callFetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

export async function sendJson<T>(
  path: string,
  method: 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<T | void> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const init: RequestInit = { method, headers }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  const res = await callFetch(path, init)
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined
  return (await res.json()) as T
}
