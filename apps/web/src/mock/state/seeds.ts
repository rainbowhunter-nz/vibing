import type { AgentSession, Devcontainer } from '../../lib/api/types'

// Single source of truth for cross-module mock identities: a given devcontainer
// or agent-session id describes the same object everywhere (detail page, inbox,
// approvals). Modules that need richer shapes (DevcontainerView, InboxEventDetail)
// layer their extra fields on top of these base records.

export const seedDevcontainers: Devcontainer[] = [
  { id: 'dc-seed-0001', name: 'my-webapp', local_path: '/home/dev/my-webapp', status: 'running', created_at: '2024-01-10T08:00:00.000Z', updated_at: '2024-01-15T10:00:00.000Z' },
  { id: 'dc-seed-0002', name: 'api-service', local_path: '/home/dev/api-service', status: 'stopped', created_at: '2024-01-11T09:00:00.000Z', updated_at: '2024-01-14T14:30:00.000Z' },
  { id: 'dc-seed-0003', name: 'data-pipeline', local_path: '/home/dev/data-pipeline', status: 'created', created_at: '2024-01-12T11:00:00.000Z', updated_at: '2024-01-12T11:00:00.000Z' },
  { id: 'dc-seed-0004', name: 'legacy-app', local_path: '/home/dev/legacy-app', status: 'error', created_at: '2024-01-08T07:00:00.000Z', updated_at: '2024-01-13T16:00:00.000Z' },
]

// dc-seed-0001 (my-webapp) carries the full status spread for inspection;
// dc-seed-0002 (api-service) has two; dc-seed-0003/0004 have none.
export const seedAgentSessions: AgentSession[] = [
  { id: 'as-seed-0001', devcontainer_id: 'dc-seed-0001', status: 'waiting_for_approval', prompt: 'Refactor the auth module', started_at: '2024-01-15T09:00:00.000Z', ended_at: null, last_event_at: '2024-01-15T09:55:00.000Z', created_at: '2024-01-15T09:00:00.000Z', updated_at: '2024-01-15T09:55:00.000Z' },
  { id: 'as-seed-0002', devcontainer_id: 'dc-seed-0002', status: 'running', prompt: 'Run the test suite', started_at: '2024-01-15T10:00:00.000Z', ended_at: null, last_event_at: '2024-01-15T10:30:00.000Z', created_at: '2024-01-15T10:00:00.000Z', updated_at: '2024-01-15T10:30:00.000Z' },
  { id: 'as-seed-0003', devcontainer_id: 'dc-seed-0002', status: 'failed', prompt: 'Deploy to staging', started_at: '2024-01-14T08:00:00.000Z', ended_at: '2024-01-14T08:45:00.000Z', last_event_at: '2024-01-14T08:45:00.000Z', created_at: '2024-01-14T08:00:00.000Z', updated_at: '2024-01-14T08:45:00.000Z' },
  { id: 'as-seed-0004', devcontainer_id: 'dc-seed-0001', status: 'completed', prompt: 'Fix the flaky test in auth', started_at: '2024-01-13T12:00:00.000Z', ended_at: '2024-01-13T12:30:00.000Z', last_event_at: '2024-01-13T12:30:00.000Z', created_at: '2024-01-13T12:00:00.000Z', updated_at: '2024-01-13T12:30:00.000Z' },
  { id: 'as-seed-0005', devcontainer_id: 'dc-seed-0001', status: 'running', prompt: 'Add logging to the API', started_at: '2024-01-15T09:30:00.000Z', ended_at: null, last_event_at: '2024-01-15T10:05:00.000Z', created_at: '2024-01-15T09:30:00.000Z', updated_at: '2024-01-15T10:05:00.000Z' },
  { id: 'as-seed-0006', devcontainer_id: 'dc-seed-0001', status: 'failed', prompt: 'Run pytest', started_at: '2024-01-13T11:00:00.000Z', ended_at: '2024-01-13T11:08:00.000Z', last_event_at: '2024-01-13T11:08:00.000Z', created_at: '2024-01-13T11:00:00.000Z', updated_at: '2024-01-13T11:08:00.000Z' },
]

export function seedDevcontainer(id: string): Devcontainer {
  const d = seedDevcontainers.find((x) => x.id === id)
  if (!d) throw new Error(`Unknown seed devcontainer: ${id}`)
  return d
}

export function seedSession(id: string): AgentSession {
  const s = seedAgentSessions.find((x) => x.id === id)
  if (!s) throw new Error(`Unknown seed session: ${id}`)
  return s
}
