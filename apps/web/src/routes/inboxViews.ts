import type { InboxEvent } from '../lib/api'

const BLOCKING = new Set<InboxEvent['event_type']>(['question', 'approval_request'])

export function isBlocking(event: InboxEvent): boolean {
  return BLOCKING.has(event.event_type)
}

function byCreatedDesc(a: InboxEvent, b: InboxEvent): number {
  return b.created_at.localeCompare(a.created_at)
}

export function needsAttentionEvents(events: InboxEvent[]): InboxEvent[] {
  const open = events.filter((e) => e.event_type !== 'completion' && e.status !== 'resolved')
  const blocking = open.filter(isBlocking).sort(byCreatedDesc)
  const failures = open.filter((e) => e.event_type === 'failure').sort(byCreatedDesc)
  return [...blocking, ...failures]
}

export function allEvents(events: InboxEvent[]): InboxEvent[] {
  return [...events].sort(byCreatedDesc)
}
