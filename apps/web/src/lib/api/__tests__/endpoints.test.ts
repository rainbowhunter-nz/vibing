import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createDevcontainer,
  deleteDevcontainer,
  fetchApprovalRequest,
  fetchDevcontainer,
  fetchInboxEvent,
  listApprovalRequests,
  listInboxEvents,
  markInboxEventRead,
  resolveAgentSessionApproval,
  resolveInboxEvent,
  sendAgentSessionUserInput,
  startAgentSession,
  startDevcontainer,
  stopAgentSession,
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

const agentSession = {
  id: 'sess-1',
  devcontainer_id: 'dc-1',
  status: 'running',
  prompt: null,
  started_at: '2024-01-01T00:00:00Z',
  ended_at: null,
  last_event_at: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('fetchAgentSession', () => {
  it('GETs /devcontainers/{id}/agent-sessions/{sid}', async () => {
    const { fetchAgentSession } = await import('../endpoints')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ...agentSession, summary_text: 'done' }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await fetchAgentSession('dc-1', 'sess-1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc-1/agent-sessions/sess-1')
    expect((init as RequestInit).method).toBeUndefined()
    expect(result.summary_text).toBe('done')
  })
})

describe('startAgentSession', () => {
  it('POSTs to /devcontainers/{id}/agent-sessions with prompt body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, { ...agentSession, status: 'starting' }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await startAgentSession('dc-1', { prompt: 'do something' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc-1/agent-sessions')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).body).toBe(JSON.stringify({ prompt: 'do something' }))
    expect(result).toEqual({ ...agentSession, status: 'starting' })
  })

  it('encodes special characters in devcontainer id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, agentSession))
    vi.stubGlobal('fetch', fetchMock)
    await startAgentSession('dc 1/x', { prompt: 'hi' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc%201%2Fx/agent-sessions')
  })
})

describe('stopAgentSession', () => {
  it('POSTs to /devcontainers/{id}/agent-sessions/{sid}/stop with no body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, { ...agentSession, status: 'stopped' }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await stopAgentSession('dc-1', 'sess-1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc-1/agent-sessions/sess-1/stop')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).body).toBeUndefined()
    expect(result).toEqual({ ...agentSession, status: 'stopped' })
  })

  it('encodes special characters in devcontainer id and session id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, agentSession))
    vi.stubGlobal('fetch', fetchMock)
    await stopAgentSession('dc 1', 'sess/2')
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc%201/agent-sessions/sess%2F2/stop')
  })
})

describe('sendAgentSessionUserInput', () => {
  it('POSTs to /devcontainers/{id}/agent-sessions/{sid}/user-input with inbox_event_id and text', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, agentSession))
    vi.stubGlobal('fetch', fetchMock)
    const result = await sendAgentSessionUserInput('dc-1', 'sess-1', { inbox_event_id: 'evt-1', text: 'yes' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc-1/agent-sessions/sess-1/user-input')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).body).toBe(JSON.stringify({ inbox_event_id: 'evt-1', text: 'yes' }))
    expect(result).toEqual(agentSession)
  })

  it('encodes special characters in devcontainer id and session id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, agentSession))
    vi.stubGlobal('fetch', fetchMock)
    await sendAgentSessionUserInput('dc 1', 'sess/2', { inbox_event_id: 'evt-1', text: 'yes' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc%201/agent-sessions/sess%2F2/user-input')
  })
})

describe('resolveAgentSessionApproval', () => {
  it('POSTs to /devcontainers/{id}/agent-sessions/{sid}/approval-resolution with approval_request_id and resolution', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, agentSession))
    vi.stubGlobal('fetch', fetchMock)
    const result = await resolveAgentSessionApproval('dc-1', 'sess-1', { approval_request_id: 'apr-1', resolution: 'approved' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc-1/agent-sessions/sess-1/approval-resolution')
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).body).toBe(JSON.stringify({ approval_request_id: 'apr-1', resolution: 'approved' }))
    expect(result).toEqual(agentSession)
  })

  it('encodes special characters in devcontainer id and session id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(202, agentSession))
    vi.stubGlobal('fetch', fetchMock)
    await resolveAgentSessionApproval('dc 1', 'sess/2', { approval_request_id: 'apr-1', resolution: 'rejected' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/devcontainers/dc%201/agent-sessions/sess%2F2/approval-resolution')
  })
})

const approvalRequest = {
  id: 'apr-1',
  devcontainer_id: 'dc-1',
  agent_session_id: 'sess-1',
  status: 'pending' as const,
  requested_action: 'run tests',
  created_at: '2024-01-01T00:00:00Z',
  decided_at: null,
}

const inboxEvent = {
  id: 'evt-1',
  devcontainer_id: 'dc-1',
  agent_session_id: 'sess-1',
  approval_request_id: null,
  event_type: 'completion' as const,
  status: 'unread',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('listInboxEvents', () => {
  it('GETs /inbox-events with no filters → bare path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [inboxEvent] }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await listInboxEvents()
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/inbox-events')
    expect(result).toEqual({ items: [inboxEvent] })
  })

  it('GETs /inbox-events with status filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await listInboxEvents({ status: 'unread' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/inbox-events?status=unread')
  })

  it('GETs /inbox-events with multiple filters using exact backend param names', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await listInboxEvents({ status: 'unread', devcontainerId: 'dc-1', agentSessionId: 'sess-1' })
    const [url] = fetchMock.mock.calls[0]
    const parsed = new URL(url, 'http://x')
    expect(parsed.pathname).toBe('/api/v1/inbox-events')
    expect(parsed.searchParams.get('status')).toBe('unread')
    expect(parsed.searchParams.get('devcontainer_id')).toBe('dc-1')
    expect(parsed.searchParams.get('agent_session_id')).toBe('sess-1')
  })

  it('omits undefined filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await listInboxEvents({ devcontainerId: 'dc-1' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/inbox-events?devcontainer_id=dc-1')
    expect(url).not.toContain('status')
    expect(url).not.toContain('agent_session_id')
  })
})

describe('fetchInboxEvent', () => {
  it('GETs /inbox-events/{id} with encoded id', async () => {
    const detail = {
      ...inboxEvent,
      devcontainer,
      agent_session: agentSession,
      approval_request: null,
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, detail))
    vi.stubGlobal('fetch', fetchMock)
    const result = await fetchInboxEvent('evt 1/x')
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/inbox-events/evt%201%2Fx')
    expect(result).toEqual(detail)
    expect(result.devcontainer).toEqual(devcontainer)
    expect(result.agent_session).toEqual(agentSession)
    expect(result.approval_request).toBeNull()
  })
})

describe('listApprovalRequests', () => {
  it('GETs /approval-requests with no filters → bare path', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [approvalRequest] }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await listApprovalRequests()
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/approval-requests')
    expect(result).toEqual({ items: [approvalRequest] })
  })

  it('GETs /approval-requests with status filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await listApprovalRequests({ status: 'pending' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/approval-requests?status=pending')
  })

  it('GETs /approval-requests with multiple filters using exact backend param names', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await listApprovalRequests({ status: 'pending', devcontainerId: 'dc-1' })
    const [url] = fetchMock.mock.calls[0]
    const parsed = new URL(url, 'http://x')
    expect(parsed.pathname).toBe('/api/v1/approval-requests')
    expect(parsed.searchParams.get('status')).toBe('pending')
    expect(parsed.searchParams.get('devcontainer_id')).toBe('dc-1')
  })

  it('omits undefined filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { items: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await listApprovalRequests({ devcontainerId: 'dc-2' })
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/approval-requests?devcontainer_id=dc-2')
    expect(url).not.toContain('status')
  })
})

describe('fetchApprovalRequest', () => {
  it('GETs /approval-requests/{id} with encoded id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, approvalRequest))
    vi.stubGlobal('fetch', fetchMock)
    const result = await fetchApprovalRequest('apr 1/x')
    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/approval-requests/apr%201%2Fx')
    expect(result).toEqual(approvalRequest)
  })
})

const inboxEventSimple = {
  id: 'evt1',
  devcontainer_id: 'dc1',
  agent_session_id: null,
  approval_request_id: null,
  event_type: 'question',
  status: 'read',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('markInboxEventRead', () => {
  it('POSTs to /inbox-events/:id/read', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, inboxEventSimple))
    vi.stubGlobal('fetch', fetchMock)
    const result = await markInboxEventRead('evt1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/inbox-events/evt1/read',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result).toEqual(inboxEventSimple)
  })
})

describe('resolveInboxEvent', () => {
  it('POSTs to /inbox-events/:id/resolve', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, inboxEventSimple))
    vi.stubGlobal('fetch', fetchMock)
    const result = await resolveInboxEvent('evt1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/inbox-events/evt1/resolve',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result).toEqual(inboxEventSimple)
  })
})
