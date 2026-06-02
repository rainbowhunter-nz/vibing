import { describe, it, expect } from 'vitest'
import { formatRelativeTime } from '../time'

describe('formatRelativeTime', () => {
  it('formats a moment ago as seconds', () => {
    const iso = new Date(Date.now() - 5_000).toISOString()
    expect(formatRelativeTime(iso)).toContain('second')
  })

  it('formats minutes in the past', () => {
    const iso = new Date(Date.now() - 5 * 60_000).toISOString()
    expect(formatRelativeTime(iso)).toContain('minute')
  })

  it('formats hours in the past', () => {
    const iso = new Date(Date.now() - 3 * 60 * 60_000).toISOString()
    expect(formatRelativeTime(iso)).toContain('hour')
  })
})
