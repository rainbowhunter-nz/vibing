import type { ApprovalRequest, ApprovalRequestList, ApprovalResolution, ApprovalStatus } from '../../lib/api/types'

// Fixed seed: one pending (cross-store ar-seed-0001), one approved, one rejected.
// ar-seed-0001 matches inbox.ts APPROVAL1 exactly (same id, devcontainer_id, agent_session_id, requested_action).
const SEED: ApprovalRequest[] = [
  {
    id: 'ar-seed-0001',
    devcontainer_id: 'dc-seed-0001',
    agent_session_id: 'as-seed-0001',
    status: 'pending',
    requested_action: 'run: pnpm migrate --env production',
    created_at: '2024-01-15T09:55:00.000Z',
    decided_at: null,
  },
  {
    id: 'ar-seed-0002',
    devcontainer_id: 'dc-seed-0001',
    agent_session_id: 'as-seed-0004',
    status: 'approved',
    requested_action: 'run: pnpm build',
    created_at: '2024-01-13T12:00:00.000Z',
    decided_at: '2024-01-13T12:05:00.000Z',
  },
  {
    id: 'ar-seed-0003',
    devcontainer_id: 'dc-seed-0001',
    agent_session_id: 'as-seed-0004',
    status: 'rejected',
    requested_action: 'run: rm -rf /tmp/build-cache',
    created_at: '2024-01-13T11:00:00.000Z',
    decided_at: '2024-01-13T11:02:00.000Z',
  },
]

let store: ApprovalRequest[] = SEED.map((r) => ({ ...r }))

export class StaleError extends Error {
  readonly code = 'APPROVAL_REQUEST_NOT_PENDING'
  constructor(id: string) {
    super(`Approval request not pending: ${id}`)
  }
}

function now(): string {
  return new Date().toISOString()
}

export function resetApprovals(): void {
  store = SEED.map((r) => ({ ...r }))
}

export function listApprovalRequests(status?: ApprovalStatus): ApprovalRequestList {
  const items = status ? store.filter((r) => r.status === status) : store
  return { items: items.map((r) => ({ ...r })) }
}

export function resolveApproval(id: string, resolution: ApprovalResolution): ApprovalRequest {
  const idx = store.findIndex((r) => r.id === id)
  // Unknown id → return success stub (keeps inbox/other flows robust)
  if (idx === -1) return { id, devcontainer_id: '', agent_session_id: '', status: resolution, requested_action: '', created_at: now(), decided_at: now() }
  if (store[idx].status !== 'pending') throw new StaleError(id)
  store[idx] = { ...store[idx], status: resolution, decided_at: now() }
  return { ...store[idx] }
}
