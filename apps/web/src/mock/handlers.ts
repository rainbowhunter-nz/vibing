import { http, HttpResponse } from 'msw'
import type { JsonBodyType, DefaultBodyType } from 'msw'
import * as f from './fixtures'
import { getScenario } from './scenario'
import type { ApiErrorEnvelope, AgentSession, DevcontainerUpdateBody } from '../lib/api/types'
import * as dc from './state/devcontainers'
import * as inbox from './state/inbox'

// Wildcard origin so handlers work in both browser (service worker) and Node (vitest/msw node).

function errorEnvelope(code: string, message: string): ApiErrorEnvelope {
  return { error: { code, message, details: null } }
}

/**
 * Returns the appropriate HttpResponse for the current scenario given the happy-path fixture.
 * - happy → baseline fixture.
 * - empty → empty collections (pass emptyValue for list endpoints).
 * - api-error → 500 error envelope.
 * - network-down → network-level failure.
 * - not-found → 404 error envelope.
 * - stale-action → 409 error envelope (richer per-route handling comes in VIB-91/92).
 */
function scenarioResponse(happy: JsonBodyType, emptyValue?: JsonBodyType): HttpResponse<DefaultBodyType> {
  const scenario = getScenario()
  switch (scenario) {
    case 'api-error':
      return HttpResponse.json(errorEnvelope('INTERNAL_ERROR', 'Simulated API error'), { status: 500 })
    case 'network-down':
      return HttpResponse.error()
    case 'not-found':
      return HttpResponse.json(errorEnvelope('NOT_FOUND', 'Simulated not found'), { status: 404 })
    case 'stale-action':
      return HttpResponse.json(errorEnvelope('CONFLICT', 'Simulated stale resource'), { status: 409 })
    case 'empty':
      return HttpResponse.json(emptyValue !== undefined ? emptyValue : happy)
    default:
      return HttpResponse.json(happy)
  }
}

/**
 * Shared scenario-failure helper for mutable-state routes (VIB-90/91/92).
 * Returns a non-null HttpResponse when the current scenario should short-circuit
 * with an error; returns null when the handler should do real store logic.
 *
 * notFoundCode — domain-specific code used for the not-found scenario (e.g. 'DEVCONTAINER_NOT_FOUND').
 */
export function scenarioFailure(notFoundCode?: string): HttpResponse<DefaultBodyType> | null {
  const scenario = getScenario()
  switch (scenario) {
    case 'api-error':
      return HttpResponse.json(errorEnvelope('INTERNAL_ERROR', 'Simulated API error'), { status: 500 })
    case 'network-down':
      return HttpResponse.error()
    case 'stale-action':
      return HttpResponse.json(errorEnvelope('CONFLICT', 'Simulated stale resource'), { status: 409 })
    case 'not-found':
      return HttpResponse.json(
        errorEnvelope(notFoundCode ?? 'NOT_FOUND', 'Simulated not found'),
        { status: 404 },
      )
    default:
      return null
  }
}

function notFoundResponse(code: string, message: string): HttpResponse<DefaultBodyType> {
  return HttpResponse.json(errorEnvelope(code, message), { status: 404 })
}

function notFound(id: string): HttpResponse<DefaultBodyType> {
  return notFoundResponse('DEVCONTAINER_NOT_FOUND', `Devcontainer not found: ${id}`)
}

const devcontainerHandlers = [
  http.get('*/api/v1/devcontainers', () => {
    const failure = scenarioFailure()
    if (failure) return failure
    const scenario = getScenario()
    if (scenario === 'empty') return HttpResponse.json({ items: [] })
    return HttpResponse.json(dc.listDevcontainers())
  }),

  http.post('*/api/v1/devcontainers', async ({ request }) => {
    const failure = scenarioFailure()
    if (failure) return failure
    const body = await request.json() as { name: string; local_path: string }
    return HttpResponse.json(dc.createDevcontainer(body), { status: 201 })
  }),

  http.get('*/api/v1/devcontainers/:id', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      return HttpResponse.json(dc.getDevcontainer(params.id as string))
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
  }),

  http.patch('*/api/v1/devcontainers/:id', async ({ params, request }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    const body = await request.json() as DevcontainerUpdateBody
    try {
      return HttpResponse.json(dc.updateDevcontainer(params.id as string, body))
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
  }),

  http.delete('*/api/v1/devcontainers/:id', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      dc.deleteDevcontainer(params.id as string)
      return new HttpResponse(null, { status: 204 })
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
  }),

  http.post('*/api/v1/devcontainers/:id/start', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      return HttpResponse.json(dc.startDevcontainer(params.id as string))
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
  }),

  http.post('*/api/v1/devcontainers/:id/stop', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      return HttpResponse.json(dc.stopDevcontainer(params.id as string))
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
  }),

  // Minimal — agent-session mutable state is out of scope (VIB-93+).
  http.get('*/api/v1/devcontainers/:id/agent-sessions', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    // Verify the devcontainer exists; return 404 for unknown ids even in happy mode.
    try {
      dc.getDevcontainer(params.id as string)
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
    return HttpResponse.json(f.agentSessions)
  }),
]

// Minimal plausible AgentSession used by agent-session action stubs
function stubSession(devcontainerId: string, sessionId: string): AgentSession {
  return {
    id: sessionId,
    devcontainer_id: devcontainerId,
    status: 'running',
    started_at: new Date().toISOString(),
    ended_at: null,
    last_event_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
}

const inboxHandlers = [
  http.get('*/api/v1/inbox-events', () => {
    const failure = scenarioFailure()
    if (failure) return failure
    const scenario = getScenario()
    if (scenario === 'empty') return HttpResponse.json({ items: [] })
    return HttpResponse.json(inbox.listInboxEvents())
  }),

  http.get('*/api/v1/inbox-events/:id', ({ params }) => {
    const failure = scenarioFailure('INBOX_EVENT_NOT_FOUND')
    if (failure) return failure
    try {
      return HttpResponse.json(inbox.getInboxEvent(params.id as string))
    } catch (e) {
      if (e instanceof inbox.NotFoundError) return notFoundResponse(e.code, e.message)
      throw e
    }
  }),

  http.post('*/api/v1/inbox-events/:id/read', ({ params }) => {
    const failure = scenarioFailure('INBOX_EVENT_NOT_FOUND')
    if (failure) return failure
    try {
      return HttpResponse.json(inbox.markInboxEventRead(params.id as string))
    } catch (e) {
      if (e instanceof inbox.NotFoundError) return notFoundResponse(e.code, e.message)
      throw e
    }
  }),

  http.post('*/api/v1/inbox-events/:id/resolve', ({ params }) => {
    const failure = scenarioFailure('INBOX_EVENT_NOT_FOUND')
    if (failure) return failure
    try {
      return HttpResponse.json(inbox.resolveInboxEvent(params.id as string))
    } catch (e) {
      if (e instanceof inbox.NotFoundError) return notFoundResponse(e.code, e.message)
      throw e
    }
  }),
]

// Minimal stubs for agent-session actions (question answer + approval resolution).
// Mutable approval state is VIB-92; these just return a plausible session so the
// UI action flow is inspectable without errors.
const agentSessionActionHandlers = [
  http.post('*/api/v1/devcontainers/:dc/agent-sessions/:sid/user-input', ({ params }) => {
    const failure = scenarioFailure()
    if (failure) return failure
    return HttpResponse.json(stubSession(params.dc as string, params.sid as string))
  }),

  http.post('*/api/v1/devcontainers/:dc/agent-sessions/:sid/approval-resolution', ({ params }) => {
    const failure = scenarioFailure()
    if (failure) return failure
    return HttpResponse.json(stubSession(params.dc as string, params.sid as string))
  }),
]

export const handlers = [
  http.get('*/api/v1/health', () => scenarioResponse(f.health)),
  http.get('*/api/v1/status', () => scenarioResponse(f.status)),
  http.get('*/api/v1/config', () => scenarioResponse(f.config)),
  http.get('*/api/v1/runtime/status', () => scenarioResponse(f.runtimeStatus)),
  http.get('*/api/v1/settings', () => scenarioResponse(f.settings)),
  http.get('*/api/v1/diagnostics', () => scenarioResponse(f.diagnostics)),
  http.get('*/api/v1/approval-requests', () => scenarioResponse(f.approvalRequests, { items: [] })),
  ...inboxHandlers,
  ...agentSessionActionHandlers,
  ...devcontainerHandlers,
]
