import { describe, it, expect } from 'vitest'
import type { TranscriptTurn } from '../../api/types'
import { emptyLiveState, liveReducer, liveOnlyTurns, mergeTurns } from '../mergeTurns'

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
  it('accumulates text by id in arrival order (coalesces into trailing text block)', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'Hel' })
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'lo' })
    expect(s.byId['a']).toEqual([{ kind: 'text', text: 'Hello' }])
    expect(s.order).toEqual(['a'])
  })

  it('keeps separate ids in arrival order (no reordering)', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'A' })
    s = liveReducer(s, { kind: 'text', turn_id: 'b', role: 'assistant', text: 'B' })
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'A2' })
    expect(s.order).toEqual(['a', 'b'])
    expect(s.byId['a']).toEqual([{ kind: 'text', text: 'AA2' }])
    expect(s.byId['b']).toEqual([{ kind: 'text', text: 'B' }])
  })

  it('run_started resets accumulated blocks', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'X' })
    s = liveReducer(s, { kind: 'run_started' })
    expect(s).toEqual(emptyLiveState())
  })

  it('run_ended sets the ended flag without dropping blocks', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'X' })
    s = liveReducer(s, { kind: 'run_ended' })
    expect(s.ended).toBe(true)
    expect(s.byId['a']).toEqual([{ kind: 'text', text: 'X' }])
  })

  it('is pure — does not mutate the input state', () => {
    const s0 = emptyLiveState()
    const s1 = liveReducer(s0, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'X' })
    expect(s0.byId).toEqual({})
    expect(s1).not.toBe(s0)
  })

  it('tool_use delta appends a tool_use block in arrival order (AC1)', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'tool_use', turn_id: 'a', name: 'Bash', summary: 'cmd=ls' })
    expect(s.byId['a']).toEqual([{ kind: 'tool_use', name: 'Bash', summary: 'cmd=ls' }])
    expect(s.order).toEqual(['a'])
  })

  it('text then tool_use then text interleaves in arrival order (AC2)', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'Let me check.' })
    s = liveReducer(s, { kind: 'tool_use', turn_id: 'a', name: 'Read', summary: 'path=/a' })
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'Done.' })
    expect(s.byId['a']).toEqual([
      { kind: 'text', text: 'Let me check.' },
      { kind: 'tool_use', name: 'Read', summary: 'path=/a' },
      { kind: 'text', text: 'Done.' },
    ])
  })

  it('text after tool_use starts a new text block (no coalesce across tool boundary)', () => {
    let s = emptyLiveState()
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'Before' })
    s = liveReducer(s, { kind: 'tool_use', turn_id: 'a', name: 'Bash', summary: 'x' })
    s = liveReducer(s, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'After' })
    expect(s.byId['a']).toHaveLength(3)
    expect(s.byId['a'][2]).toEqual({ kind: 'text', text: 'After' })
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

  it('does NOT duplicate a turn once it lands in the transcript (reconcile by id, AC3)', () => {
    // Live streamed assistant 'a1'; after refetch the transcript now contains 'a1'.
    const transcript = [userTurn('u1', 'hi'), assistantTurn('a1', 'Hello there')]
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a1', role: 'assistant', text: 'Hello' })
    const merged = mergeTurns(transcript, live)
    // Only the canonical transcript turn appears — no duplicate live bubble.
    expect(merged).toEqual(transcript)
    expect(merged.filter((t) => t.id === 'a1')).toHaveLength(1)
  })

  it('does NOT duplicate live tool cards once transcript contains the turn (AC3)', () => {
    const transcript = [
      userTurn('u1', 'hi'),
      {
        id: 'a1',
        role: 'assistant' as const,
        blocks: [
          { kind: 'tool_use' as const, name: 'Bash', summary: 'cmd=ls' },
          { kind: 'text' as const, text: 'Done.' },
        ],
        at: '',
      },
    ]
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'tool_use', turn_id: 'a1', name: 'Bash', summary: 'cmd=ls' })
    live = liveReducer(live, { kind: 'text', turn_id: 'a1', role: 'assistant', text: 'Done.' })
    const merged = mergeTurns(transcript, live)
    expect(merged).toEqual(transcript)
    expect(merged.filter((t) => t.id === 'a1')).toHaveLength(1)
  })

  it('drops live bubbles once run ends even when transcript turn ids differ', () => {
    const transcript = [userTurn('u1', 'hi'), assistantTurn('canonical-id', 'Hello there')]
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'stream-id', role: 'assistant', text: 'Hello there' })
    live = liveReducer(live, { kind: 'run_ended' })
    const baseline = new Set(['u1', 'canonical-id'])
    expect(liveOnlyTurns(transcript, live, false, baseline)).toEqual([])
    expect(mergeTurns(transcript, live, false, baseline)).toEqual(transcript)
  })

  it('keeps live bubbles after run ends when transcript refetch is still empty', () => {
    const transcript: TranscriptTurn[] = []
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'stream-id', role: 'assistant', text: 'Hello there' })
    live = liveReducer(live, { kind: 'run_ended' })
    expect(liveOnlyTurns(transcript, live, false, new Set())).toEqual([
      assistantTurn('stream-id', 'Hello there'),
    ])
  })

  it('keeps live bubbles visible while transcript refetch is in flight after run ends', () => {
    const transcript = [userTurn('u1', 'hi')]
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'stream-id', role: 'assistant', text: 'Hello there' })
    live = liveReducer(live, { kind: 'run_ended' })
    expect(liveOnlyTurns(transcript, live, true)).toEqual([assistantTurn('stream-id', 'Hello there')])
  })

  it('preserves transcript order and does not reorder', () => {
    const transcript = [userTurn('u1', 'a'), assistantTurn('a1', 'b'), userTurn('u2', 'c')]
    const merged = mergeTurns(transcript, emptyLiveState())
    expect(merged.map((t) => t.id)).toEqual(['u1', 'a1', 'u2'])
  })

  it('ignores empty live blocks (no blank bubbles)', () => {
    const transcript = [userTurn('u1', 'hi')]
    const live = { byId: { a1: [] }, order: ['a1'], ended: false }
    expect(mergeTurns(transcript, live)).toEqual(transcript)
  })

  it('multiple live-only bubbles render in arrival order', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a', role: 'assistant', text: 'A' })
    live = liveReducer(live, { kind: 'text', turn_id: 'b', role: 'assistant', text: 'B' })
    const merged = mergeTurns([], live)
    expect(merged.map((t) => t.id)).toEqual(['a', 'b'])
  })

  it('live turn with mixed text+tool blocks renders in block arrival order (AC1+AC2)', () => {
    let live = emptyLiveState()
    live = liveReducer(live, { kind: 'text', turn_id: 'a1', role: 'assistant', text: 'Looking…' })
    live = liveReducer(live, { kind: 'tool_use', turn_id: 'a1', name: 'Bash', summary: 'cmd=ls' })
    live = liveReducer(live, { kind: 'text', turn_id: 'a1', role: 'assistant', text: 'Done.' })
    const merged = mergeTurns([], live)
    expect(merged).toHaveLength(1)
    expect(merged[0].blocks).toEqual([
      { kind: 'text', text: 'Looking…' },
      { kind: 'tool_use', name: 'Bash', summary: 'cmd=ls' },
      { kind: 'text', text: 'Done.' },
    ])
  })
})
