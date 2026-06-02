import { describe, it, expect } from 'vitest'
import { needsAttentionEvents, allEvents } from '../inboxViews'
import type { InboxEvent } from '../../lib/api'

function ev(over: Partial<InboxEvent>): InboxEvent {
  return {
    id: 'x',
    devcontainer_id: 'dc',
    agent_session_id: 'as',
    approval_request_id: null,
    event_type: 'question',
    status: 'unread',
    created_at: '2026-06-03T00:00:00Z',
    updated_at: '2026-06-03T00:00:00Z',
    ...over,
  }
}

describe('needsAttentionEvents', () => {
  it('excludes completions and resolved events', () => {
    const events = [
      ev({ id: 'q', event_type: 'question' }),
      ev({ id: 'done', event_type: 'completion' }),
      ev({ id: 'resolved-q', event_type: 'question', status: 'resolved' }),
    ]
    expect(needsAttentionEvents(events).map((e) => e.id)).toEqual(['q'])
  })

  it('orders blocking items (question, approval_request) before failures', () => {
    const events = [
      ev({ id: 'f', event_type: 'failure' }),
      ev({ id: 'a', event_type: 'approval_request' }),
      ev({ id: 'q', event_type: 'question' }),
    ]
    const ids = needsAttentionEvents(events).map((e) => e.id)
    expect(ids.indexOf('q')).toBeLessThan(ids.indexOf('f'))
    expect(ids.indexOf('a')).toBeLessThan(ids.indexOf('f'))
  })

  it('orders newest first within a group', () => {
    const events = [
      ev({ id: 'old', event_type: 'question', created_at: '2026-06-01T00:00:00Z' }),
      ev({ id: 'new', event_type: 'question', created_at: '2026-06-03T00:00:00Z' }),
    ]
    expect(needsAttentionEvents(events).map((e) => e.id)).toEqual(['new', 'old'])
  })
})

describe('allEvents', () => {
  it('includes completions and resolved events, newest first', () => {
    const events = [
      ev({ id: 'old', event_type: 'completion', created_at: '2026-06-01T00:00:00Z' }),
      ev({ id: 'new', event_type: 'question', status: 'resolved', created_at: '2026-06-03T00:00:00Z' }),
    ]
    expect(allEvents(events).map((e) => e.id)).toEqual(['new', 'old'])
  })
})
