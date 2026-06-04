import { http, HttpResponse } from 'msw'
import type { JsonBodyType, DefaultBodyType } from 'msw'
import * as f from './fixtures'
import { getScenario } from './scenario'
import type { ApiErrorEnvelope } from '../lib/api/types'

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
 * - stale-action → 409 error envelope (richer per-route handling comes in VIB-90/91/92).
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

export const handlers = [
  http.get('*/api/v1/health', () => scenarioResponse(f.health)),
  http.get('*/api/v1/status', () => scenarioResponse(f.status)),
  http.get('*/api/v1/config', () => scenarioResponse(f.config)),
  http.get('*/api/v1/runtime/status', () => scenarioResponse(f.runtimeStatus)),
  http.get('*/api/v1/settings', () => scenarioResponse(f.settings)),
  http.get('*/api/v1/diagnostics', () => scenarioResponse(f.diagnostics)),
  http.get('*/api/v1/devcontainers', () => scenarioResponse(f.devcontainers, { items: [] })),
  http.get('*/api/v1/inbox-events', () => scenarioResponse(f.inboxEvents, { items: [] })),
  http.get('*/api/v1/approval-requests', () => scenarioResponse(f.approvalRequests, { items: [] })),
]
