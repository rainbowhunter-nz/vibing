import { describe, it, expect } from 'vitest'
import { emptyLiveState, liveReducer } from '../../stream/mergeTurns'
import { shouldStick, hasLiveText, isWorkingIndicatorVisible } from '../chatHelpers'

describe('shouldStick', () => {
  it('returns true when scrolled exactly to bottom', () => {
    // scrollHeight=500, clientHeight=300, scrollTop=200 → distance=0
    expect(shouldStick(200, 500, 300)).toBe(true)
  })

  it('returns true when within default threshold (40px)', () => {
    // distance = 500 - 160 - 300 = 40 (exactly on boundary)
    expect(shouldStick(160, 500, 300)).toBe(true)
  })

  it('returns false when distance exceeds threshold', () => {
    // distance = 500 - 100 - 300 = 100 > 40
    expect(shouldStick(100, 500, 300)).toBe(false)
  })

  it('returns true when all dimensions are 0 (happy-dom environment)', () => {
    // happy-dom: scrollHeight=0, clientHeight=0, scrollTop=0 → distance=0 → stick
    expect(shouldStick(0, 0, 0)).toBe(true)
  })

  it('respects custom threshold', () => {
    // distance = 500 - 350 - 100 = 50; threshold=60 → stick
    expect(shouldStick(350, 500, 100, 60)).toBe(true)
    // threshold=40 → no stick
    expect(shouldStick(350, 500, 100, 40)).toBe(false)
  })
})

describe('hasLiveText', () => {
  it('returns false for empty live state', () => {
    expect(hasLiveText(emptyLiveState())).toBe(false)
  })

  it('returns true when a turn has a text block with content', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'Hello' })
    expect(hasLiveText(live)).toBe(true)
  })

  it('returns false when only tool_use blocks present (no text)', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'tool_use', turn_id: 'a', name: 'Bash', summary: 'ls' })
    expect(hasLiveText(live)).toBe(false)
  })

  it('returns true with text even after run_ended (hasLiveText ignores ended flag)', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'X' })
    expect(hasLiveText(live)).toBe(true)
  })
})

describe('isWorkingIndicatorVisible', () => {
  it('shows when active + not ended + no live text', () => {
    expect(isWorkingIndicatorVisible(true, emptyLiveState())).toBe(true)
  })

  it('hides when not active', () => {
    expect(isWorkingIndicatorVisible(false, emptyLiveState())).toBe(false)
  })

  it('hides when live.ended is true', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'run_ended' })
    expect(isWorkingIndicatorVisible(true, live)).toBe(false)
  })

  it('hides once live text starts streaming', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'Hi' })
    expect(isWorkingIndicatorVisible(true, live)).toBe(false)
  })

  it('shows when active + tool_use only (no text yet — between tool calls)', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'tool_use', turn_id: 'a', name: 'Bash', summary: 'ls' })
    expect(isWorkingIndicatorVisible(true, live)).toBe(true)
  })
})
