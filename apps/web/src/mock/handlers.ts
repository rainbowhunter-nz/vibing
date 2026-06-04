import { http, HttpResponse } from 'msw'
import * as f from './fixtures'

// Wildcard origin so handlers work in both browser (service worker) and Node (vitest/msw node).
// VIB-89 will extend with scenarios; VIB-90/91/92 add mutable state and writes.
export const handlers = [
  http.get('*/api/v1/health', () => HttpResponse.json(f.health)),
  http.get('*/api/v1/status', () => HttpResponse.json(f.status)),
  http.get('*/api/v1/config', () => HttpResponse.json(f.config)),
  http.get('*/api/v1/runtime/status', () => HttpResponse.json(f.runtimeStatus)),
  http.get('*/api/v1/settings', () => HttpResponse.json(f.settings)),
  http.get('*/api/v1/diagnostics', () => HttpResponse.json(f.diagnostics)),
  http.get('*/api/v1/devcontainers', () => HttpResponse.json(f.devcontainers)),
  http.get('*/api/v1/inbox-events', () => HttpResponse.json(f.inboxEvents)),
  http.get('*/api/v1/approval-requests', () => HttpResponse.json(f.approvalRequests)),
]
