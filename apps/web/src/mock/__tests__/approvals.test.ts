import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { setScenario, resetScenario } from '../scenario'
import { resetApprovals } from '../state/approvals'
import { resetInbox } from '../state/inbox'
import { resetDevcontainers } from '../state/devcontainers'

const server = setupServer(...handlers)

beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetDevcontainers(); resetInbox(); resetApprovals() })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

async function get(path: string) {
  return fetch(`http://localhost${path}`)
}

async function post(path: string, body?: unknown) {
  return fetch(`http://localhost${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
}

// ---------------------------------------------------------------------------
// GET /api/v1/approval-requests (list)
// ---------------------------------------------------------------------------

describe('GET /api/v1/approval-requests', () => {
  it('happy — returns store items for pending tab', async () => {
    const res = await get('/api/v1/approval-requests?status=pending')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items.every((r: { status: string }) => r.status === 'pending')).toBe(true)
    expect(body.items.length).toBeGreaterThanOrEqual(1)
  })

  it('happy — returns store items for approved tab', async () => {
    const res = await get('/api/v1/approval-requests?status=approved')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items.every((r: { status: string }) => r.status === 'approved')).toBe(true)
    expect(body.items.length).toBeGreaterThanOrEqual(1)
  })

  it('happy — returns store items for rejected tab', async () => {
    const res = await get('/api/v1/approval-requests?status=rejected')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items.every((r: { status: string }) => r.status === 'rejected')).toBe(true)
    expect(body.items.length).toBeGreaterThanOrEqual(1)
  })

  it('happy — no filter returns all items', async () => {
    const res = await get('/api/v1/approval-requests')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items.length).toBeGreaterThanOrEqual(3)
  })

  it('empty scenario — returns empty items', async () => {
    setScenario('empty')
    const res = await get('/api/v1/approval-requests?status=pending')
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.items).toEqual([])
  })

  it('api-error scenario — returns 500', async () => {
    setScenario('api-error')
    const res = await get('/api/v1/approval-requests')
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error.code).toBe('INTERNAL_ERROR')
  })

  it('network-down scenario — fetch rejects', async () => {
    setScenario('network-down')
    await expect(get('/api/v1/approval-requests')).rejects.toThrow()
  })
})

// ---------------------------------------------------------------------------
// POST .../approval-resolution (AC2: mutates store; AC5: stale)
// ---------------------------------------------------------------------------

describe('POST /api/v1/devcontainers/:dc/agent-sessions/:sid/approval-resolution', () => {
  it('happy — resolves pending → approved and returns AgentSession stub', async () => {
    const res = await post(
      '/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0001/approval-resolution',
      { approval_request_id: 'ar-seed-0001', resolution: 'approved' },
    )
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.id).toBe('as-seed-0001')
    expect(body.devcontainer_id).toBe('dc-seed-0001')
  })

  it('AC2: resolve then list — moved out of pending into approved', async () => {
    await post(
      '/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0001/approval-resolution',
      { approval_request_id: 'ar-seed-0001', resolution: 'approved' },
    )
    const pendingRes = await get('/api/v1/approval-requests?status=pending')
    const pendingBody = await pendingRes.json()
    expect(pendingBody.items.some((r: { id: string }) => r.id === 'ar-seed-0001')).toBe(false)

    const approvedRes = await get('/api/v1/approval-requests?status=approved')
    const approvedBody = await approvedRes.json()
    expect(approvedBody.items.some((r: { id: string }) => r.id === 'ar-seed-0001')).toBe(true)
  })

  it('AC5: resolving already-resolved → 409 APPROVAL_REQUEST_NOT_PENDING', async () => {
    await post(
      '/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0001/approval-resolution',
      { approval_request_id: 'ar-seed-0001', resolution: 'approved' },
    )
    const res = await post(
      '/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0001/approval-resolution',
      { approval_request_id: 'ar-seed-0001', resolution: 'rejected' },
    )
    expect(res.status).toBe(409)
    const body = await res.json()
    expect(body.error.code).toBe('APPROVAL_REQUEST_NOT_PENDING')
  })

  it('stale-action scenario — 409 APPROVAL_REQUEST_NOT_PENDING (not generic CONFLICT)', async () => {
    setScenario('stale-action')
    const res = await post(
      '/api/v1/devcontainers/dc1/agent-sessions/as1/approval-resolution',
      { approval_request_id: 'ar1', resolution: 'approved' },
    )
    expect(res.status).toBe(409)
    const body = await res.json()
    expect(body.error.code).toBe('APPROVAL_REQUEST_NOT_PENDING')
  })

  it('api-error scenario — returns 500 (generic resolution failure)', async () => {
    setScenario('api-error')
    const res = await post(
      '/api/v1/devcontainers/dc1/agent-sessions/as1/approval-resolution',
      { approval_request_id: 'ar1', resolution: 'approved' },
    )
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error.code).toBe('INTERNAL_ERROR')
  })

  it('unknown approval_request_id — returns success stub (keeps other flows robust)', async () => {
    const res = await post(
      '/api/v1/devcontainers/dc1/agent-sessions/as1/approval-resolution',
      { approval_request_id: 'nonexistent-ar', resolution: 'approved' },
    )
    expect(res.status).toBe(200)
  })

  it('VIB-91 regression: inbox approval flow still works (ar-seed-0001 resolves successfully)', async () => {
    const res = await post(
      '/api/v1/devcontainers/dc-seed-0001/agent-sessions/as-seed-0001/approval-resolution',
      { approval_request_id: 'ar-seed-0001', resolution: 'approved' },
    )
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('id')
    expect(body).toHaveProperty('status')
  })
})
