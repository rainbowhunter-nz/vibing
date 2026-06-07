import { describe, it, expect } from 'vitest'
import type { TranscriptTurn } from '../../api/types'
import { emptyLiveState, liveReducer, mergeTurns } from '../mergeTurns'

const userTurn = (id: string, text: string): TranscriptTurn => ({
  id,
  role: 'user',
  blocks: [{ kind: 'text', text }],
  at: '',
})

const assistantTurn = (id: string, text: string): TranscriptTurn => ({
  id,
  role: 'assistant',
  blocks: [{ kind: 'text', text }],
  at: '',
})

describe('liveReducer', () => {
  it('accumulates text by id in arrival order', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'Hel' })
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'lo' })
    expect(s.byId).toEqual({ a: 'Hello' })
    expect(s.order).toEqual(['a'])
  })

  it('keeps separate ids in arrival order (no reordering)', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'A' })
    s = liveReducer(s, { kind: 'text', turn_id: 'b', role: 'assistant', text: 'B' })
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'A2' })
    expect(s.order).toEqual(['a', 'b'])
    expect(s.byId).toEqual({ a: 'AA2', b: 'B' })
  })

  it('run_started resets accumulated text', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'X' })
    s = liveReducer(s, { kind: 'run_started' })
    expect(s).toEqual(emptyLiveState())
  })

  it('run_ended sets the ended flag without dropping text', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'X' })
    s = liveReducer(s, { kind: 'run_ended' })
    expect(s.ended).toBe(true)
    expect(s.byId).toEqual({ a: 'X' })
  })

  it('is pure — does not mutate the input state', () => {
    const s0 = emptyLiveState()
    const s1 = liveReducer(s0, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'X' })
    expect(s0.byId).toEqual({})
    expect(s1).not.toBe(s0)
  })
})

describe('mergeTurns', () => {
  it('renders live-only assistant text as a new in-progress bubble after the transcript', () => {
    const transcript = [userTurn('u1', 'hi')]
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a1', role: 'assistant', text: 'typing…' })
    const merged = mergeTurns(transcript, live)
    expect(merged).toEqual([
      userTurn('u1', 'hi'),
      assistantTurn('a1', 'typing…'),
    ])
  })

  it('does NOT duplicate a turn once it lands in the transcript (reconcile by id)', () => {
    // Live streamed assistant 'a1'; after refetch the transcript now contains 'a1'.
    const transcript = [userTurn('u1', 'hi'), assistantTurn('a1', 'Hello there')]
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a1', role: 'assistant', text: 'Hello' })
    const merged = mergeTurns(transcript, live)
    // Only the canonical transcript turn appears — no duplicate live bubble.
    expect(merged).toEqual(transcript)
    expect(merged.filter((t) => t.id === 'a1')).toHaveLength(1)
  })

  it('preserves transcript order and does not reorder', () => {
    const transcript = [userTurn('u1', 'a'), assistantTurn('a1', 'b'), userTurn('u2', 'c')]
    const merged = mergeTurns(transcript, emptyLiveState())
    expect(merged.map((t) => t.id)).toEqual(['u1', 'a1', 'u2'])
  })

  it('ignores empty live text (no blank bubbles)', () => {
    const transcript = [userTurn('u1', 'hi')]
    const live = { byId: { a1: '' }, order: ['a1'], ended: false }
    expect(mergeTurns(transcript, live)).toEqual(transcript)
  })

  it('multiple live-only bubbles render in arrival order', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'A' })
    live = liveReducer(live, { kind: 'text', turn_id: 'b', role: 'assistant', text: 'B' })
    const merged = mergeTurns([], live)
    expect(merged.map((t) => t.id)).toEqual(['a', 'b'])
  })
})
