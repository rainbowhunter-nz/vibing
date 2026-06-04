import { describe, it, expect, beforeEach } from 'vitest'
import {
  resetApprovals,
  listApprovalRequests,
  resolveApproval,
  StaleError,
} from '../approvals'

beforeEach(() => resetApprovals())

describe('listApprovalRequests', () => {
  it('returns all seeded items with no filter', () => {
    const { items } = listApprovalRequests()
    expect(items.length).toBeGreaterThanOrEqual(3)
    const statuses = items.map((r) => r.status)
    expect(statuses).toContain('pending')
    expect(statuses).toContain('approved')
    expect(statuses).toContain('rejected')
  })

  it('filters by pending', () => {
    const { items } = listApprovalRequests('pending')
    expect(items.every((r) => r.status === 'pending')).toBe(true)
    expect(items.length).toBeGreaterThanOrEqual(1)
  })

  it('filters by approved', () => {
    const { items } = listApprovalRequests('approved')
    expect(items.every((r) => r.status === 'approved')).toBe(true)
    expect(items.length).toBeGreaterThanOrEqual(1)
  })

  it('filters by rejected', () => {
    const { items } = listApprovalRequests('rejected')
    expect(items.every((r) => r.status === 'rejected')).toBe(true)
    expect(items.length).toBeGreaterThanOrEqual(1)
  })

  it('returns deep copies (mutation does not affect store)', () => {
    const { items } = listApprovalRequests()
    const first = items[0]
    first.status = 'approved'
    const again = listApprovalRequests().items.find((r) => r.id === first.id)
    expect(again?.status).not.toBe('approved')
  })

  it('includes ar-seed-0001 as pending', () => {
    const { items } = listApprovalRequests('pending')
    expect(items.some((r) => r.id === 'ar-seed-0001')).toBe(true)
  })

  it('ar-seed-0001 has correct cross-store fields', () => {
    const { items } = listApprovalRequests('pending')
    const ar = items.find((r) => r.id === 'ar-seed-0001')
    expect(ar?.devcontainer_id).toBe('dc-seed-0001')
    expect(ar?.requested_action).toBe('run: pnpm migrate --env production')
  })
})

describe('resolveApproval', () => {
  it('pending → approved: sets status and decided_at', () => {
    const result = resolveApproval('ar-seed-0001', 'approved')
    expect(result.status).toBe('approved')
    expect(result.decided_at).not.toBeNull()
  })

  it('pending → rejected: sets status and decided_at', () => {
    const result = resolveApproval('ar-seed-0001', 'rejected')
    expect(result.status).toBe('rejected')
    expect(result.decided_at).not.toBeNull()
  })

  it('persists: list shows moved out of pending', () => {
    resolveApproval('ar-seed-0001', 'approved')
    const pending = listApprovalRequests('pending').items
    expect(pending.some((r) => r.id === 'ar-seed-0001')).toBe(false)
    const approved = listApprovalRequests('approved').items
    expect(approved.some((r) => r.id === 'ar-seed-0001')).toBe(true)
  })

  it('already-approved → StaleError with code APPROVAL_REQUEST_NOT_PENDING', () => {
    resolveApproval('ar-seed-0001', 'approved')
    expect(() => resolveApproval('ar-seed-0001', 'rejected')).toThrow(StaleError)
    const err = (() => { try { resolveApproval('ar-seed-0001', 'rejected') } catch (e) { return e } })()
    expect((err as StaleError).code).toBe('APPROVAL_REQUEST_NOT_PENDING')
  })

  it('already-rejected → StaleError', () => {
    // find a seeded rejected entry
    const rejected = listApprovalRequests('rejected').items[0]
    expect(() => resolveApproval(rejected.id, 'approved')).toThrow(StaleError)
  })

  it('unknown id → returns success stub (does not throw)', () => {
    // per spec: unknown id → success, keeps inbox/other flows robust
    expect(() => resolveApproval('nonexistent-id', 'approved')).not.toThrow()
  })
})

describe('resetApprovals', () => {
  it('restores seed after mutations', () => {
    resolveApproval('ar-seed-0001', 'approved')
    resetApprovals()
    const pending = listApprovalRequests('pending').items
    expect(pending.some((r) => r.id === 'ar-seed-0001')).toBe(true)
  })
})
