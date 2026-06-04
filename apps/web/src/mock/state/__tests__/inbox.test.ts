import { describe, it, expect, beforeEach } from 'vitest'
import {
  resetInbox,
  listInboxEvents,
  getInboxEvent,
  markInboxEventRead,
  resolveInboxEvent,
  NotFoundError,
} from '../inbox'

beforeEach(() => resetInbox())

describe('listInboxEvents', () => {
  it('returns all 4 seeded event types', () => {
    const { items } = listInboxEvents()
    expect(items.length).toBe(4)
    const types = items.map((e) => e.event_type)
    expect(types).toContain('question')
    expect(types).toContain('approval_request')
    expect(types).toContain('completion')
    expect(types).toContain('failure')
  })

  it('returns InboxEvent shape (no detail fields)', () => {
    const { items } = listInboxEvents()
    for (const item of items) {
      expect(item).not.toHaveProperty('content')
      expect(item).not.toHaveProperty('devcontainer')
      expect(item).not.toHaveProperty('agent_session')
      expect(item).not.toHaveProperty('approval_request')
      expect(item).toHaveProperty('id')
      expect(item).toHaveProperty('event_type')
      expect(item).toHaveProperty('status')
    }
  })

  it('includes at least one unread question, unread approval_request, unread failure, resolved completion', () => {
    const { items } = listInboxEvents()
    expect(items.some((e) => e.event_type === 'question' && e.status === 'unread')).toBe(true)
    expect(items.some((e) => e.event_type === 'approval_request' && e.status === 'unread')).toBe(true)
    expect(items.some((e) => e.event_type === 'failure' && e.status === 'unread')).toBe(true)
    expect(items.some((e) => e.event_type === 'completion' && e.status === 'resolved')).toBe(true)
  })
})

describe('getInboxEvent', () => {
  it('returns InboxEventDetail for a seeded id', () => {
    const detail = getInboxEvent('ie-seed-0001')
    expect(detail.id).toBe('ie-seed-0001')
    expect(detail.event_type).toBe('question')
    expect(detail).toHaveProperty('content')
    expect(detail).toHaveProperty('devcontainer')
    expect(detail.devcontainer).toHaveProperty('name')
    expect(detail).toHaveProperty('agent_session')
    expect(detail).toHaveProperty('approval_request')
  })

  it('returns a deep copy (mutation does not affect store)', () => {
    const detail = getInboxEvent('ie-seed-0001')
    detail.status = 'resolved'
    detail.devcontainer.name = 'mutated'
    const again = getInboxEvent('ie-seed-0001')
    expect(again.status).toBe('unread')
    expect(again.devcontainer.name).not.toBe('mutated')
  })

  it('throws NotFoundError with code INBOX_EVENT_NOT_FOUND for unknown id', () => {
    expect(() => getInboxEvent('nonexistent')).toThrow(NotFoundError)
    const err = (() => { try { getInboxEvent('x') } catch (e) { return e } })()
    expect((err as NotFoundError).code).toBe('INBOX_EVENT_NOT_FOUND')
    expect((err as NotFoundError).message).toMatch(/x/)
  })
})

describe('markInboxEventRead', () => {
  it('flips unread → read', () => {
    const result = markInboxEventRead('ie-seed-0001')
    expect(result.status).toBe('read')
  })

  it('persists the change so a later get reflects it', () => {
    markInboxEventRead('ie-seed-0001')
    expect(getInboxEvent('ie-seed-0001').status).toBe('read')
    expect(listInboxEvents().items.find((e) => e.id === 'ie-seed-0001')?.status).toBe('read')
  })

  it('bumps updated_at', () => {
    const before = getInboxEvent('ie-seed-0001').updated_at
    markInboxEventRead('ie-seed-0001')
    const after = getInboxEvent('ie-seed-0001').updated_at
    expect(after >= before).toBe(true)
  })

  it('throws NotFoundError for unknown id', () => {
    expect(() => markInboxEventRead('nope')).toThrow(NotFoundError)
  })
})

describe('resolveInboxEvent', () => {
  it('flips status → resolved', () => {
    const result = resolveInboxEvent('ie-seed-0002')
    expect(result.status).toBe('resolved')
  })

  it('persists the change', () => {
    resolveInboxEvent('ie-seed-0002')
    expect(getInboxEvent('ie-seed-0002').status).toBe('resolved')
  })

  it('throws NotFoundError for unknown id', () => {
    expect(() => resolveInboxEvent('nope')).toThrow(NotFoundError)
  })
})

describe('resetInbox', () => {
  it('restores seed after mutations', () => {
    markInboxEventRead('ie-seed-0001')
    resolveInboxEvent('ie-seed-0002')
    resetInbox()
    expect(getInboxEvent('ie-seed-0001').status).toBe('unread')
    expect(getInboxEvent('ie-seed-0002').status).toBe('unread')
    expect(listInboxEvents().items.length).toBe(4)
  })
})
