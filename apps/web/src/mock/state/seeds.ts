import type { Devcontainer, DelegatedRun, HarnessStatus } from '../../lib/api/types'

// Single source of truth for cross-module mock identities: a given devcontainer id
// describes the same object everywhere. Modules that need richer shapes (DevcontainerView)
// layer their extra fields on top of these.

export const seedDevcontainers: Devcontainer[] = [
  { id: 'dc-seed-0001', name: 'my-webapp', local_path: '/home/dev/my-webapp', status: 'running', created_at: '2024-01-10T08:00:00.000Z', updated_at: '2024-01-15T10:00:00.000Z' },
  { id: 'dc-seed-0002', name: 'api-service', local_path: '/home/dev/api-service', status: 'stopped', created_at: '2024-01-11T09:00:00.000Z', updated_at: '2024-01-14T14:30:00.000Z' },
  { id: 'dc-seed-0003', name: 'data-pipeline', local_path: '/home/dev/data-pipeline', status: 'created', created_at: '2024-01-12T11:00:00.000Z', updated_at: '2024-01-12T11:00:00.000Z' },
  { id: 'dc-seed-0004', name: 'legacy-app', local_path: '/home/dev/legacy-app', status: 'error', created_at: '2024-01-08T07:00:00.000Z', updated_at: '2024-01-13T16:00:00.000Z' },
]

// Harness status per devcontainer. dc-seed-0001 spans all three states for inspection.
export const seedHarnesses: Record<string, HarnessStatus[]> = {
  'dc-seed-0001': [
    { name: 'claude-code', installed: true, authenticated: true },
    { name: 'codex', installed: true, authenticated: false },
    { name: 'cursor', installed: false, authenticated: false },
  ],
  'dc-seed-0002': [
    { name: 'claude-code', installed: true, authenticated: false },
    { name: 'codex', installed: false, authenticated: false },
    { name: 'cursor', installed: false, authenticated: false },
  ],
}

// Delegated runs per devcontainer. dc-seed-0001 carries live runs plus a history of
// terminal states; the detail page surfaces only the running ones.
export const seedDelegatedRuns: Record<string, DelegatedRun[]> = {
  'dc-seed-0001': [
    { run_id: 'run-9', harness: 'claude-code', model: 'opus-4.8', status: 'running', result: null, error: null, started_at: '2024-01-15T10:20:00.000Z' },
    { run_id: 'run-8', harness: 'cursor', model: 'auto', status: 'running', result: null, error: null, started_at: '2024-01-15T10:15:00.000Z' },
    { run_id: 'run-7', harness: 'codex', model: 'gpt-5-codex', status: 'running', result: null, error: null, started_at: '2024-01-15T10:10:00.000Z' },
    { run_id: 'run-6', harness: 'claude-code', model: 'opus-4.8', status: 'running', result: null, error: null, started_at: '2024-01-15T10:05:00.000Z' },
    { run_id: 'run-4', harness: 'codex', model: 'gpt-5-codex', status: 'running', result: null, error: null, started_at: '2024-01-15T10:00:00.000Z' },
    { run_id: 'run-3', harness: 'claude-code', model: 'opus-4.8', status: 'completed', result: 'Refactored auth module; 3 files changed, tests pass.', error: null, started_at: '2024-01-15T09:55:00.000Z' },
    { run_id: 'run-2', harness: 'cursor', model: 'auto', status: 'failed', result: null, error: { exit_code: 1, stderr_tail: 'ENOENT: package.json not found' }, started_at: '2024-01-15T09:40:00.000Z' },
    { run_id: 'run-1', harness: 'codex', model: 'gpt-5-codex', status: 'stopped', result: null, error: null, started_at: '2024-01-15T09:20:00.000Z' },
    { run_id: 'run-0', harness: 'claude-code', model: 'opus-4.8', status: 'completed', result: 'Added unit tests for the parser; coverage 84% → 91%.', error: null, started_at: '2024-01-15T08:50:00.000Z' },
  ],
}

export function seedDevcontainer(id: string): Devcontainer {
  const d = seedDevcontainers.find((x) => x.id === id)
  if (!d) throw new Error(`Unknown seed devcontainer: ${id}`)
  return d
}
