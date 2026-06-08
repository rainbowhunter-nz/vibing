// Pure turn-merge reducer (ADR-0010, VIB-109/110): merges live text + tool_use deltas
// with the canonical transcript, keyed by turn id. Blocks accumulate in arrival order
// (text coalesces with the trailing text block; tool_use always starts a new block);
// on the terminal run_ended the caller refetches the transcript and this merge reconciles
// by id — live blocks for ids now in the transcript are dropped in favor of the canonical turn.

import type { TextDelta, ToolUseDelta, TranscriptBlock, TranscriptTurn, TurnDelta } from '../api/types'

// Accumulated live blocks for the current run, keyed by turn id, preserving arrival order.
export interface LiveState {
  byId: Record<string, TranscriptBlock[]>
  order: string[]
  // True once the run's terminal delta arrived; the view then reconciles to transcript.
  ended: boolean
}

export const emptyLiveState = (): LiveState => ({ byId: {}, order: [], ended: false })

// Fold one delta into the live state. Pure: returns a new state, never mutates.
export function liveReducer(state: LiveState, delta: TurnDelta): LiveState {
  switch (delta.kind) {
    case 'run_started':
      return emptyLiveState()
    case 'run_ended':
      return { ...state, ended: true }
    case 'text':
      return appendText(state, delta)
    case 'tool_use':
      return appendToolUse(state, delta)
  }
}

function ensureOrder(state: LiveState, turnId: string): string[] {
  return turnId in state.byId ? state.order : [...state.order, turnId]
}

function appendText(state: LiveState, delta: TextDelta): LiveState {
  const blocks = state.byId[delta.turn_id] ?? []
  const last = blocks[blocks.length - 1]
  let newBlocks: TranscriptBlock[]
  if (last && last.kind === 'text') {
    // Coalesce into the trailing text block.
    newBlocks = [...blocks.slice(0, -1), { kind: 'text' as const, text: last.text + delta.text }]
  } else {
    newBlocks = [...blocks, { kind: 'text' as const, text: delta.text }]
  }
  return {
    ...state,
    byId: { ...state.byId, [delta.turn_id]: newBlocks },
    order: ensureOrder(state, delta.turn_id),
  }
}

function appendToolUse(state: LiveState, delta: ToolUseDelta): LiveState {
  const blocks = state.byId[delta.turn_id] ?? []
  return {
    ...state,
    byId: {
      ...state.byId,
      [delta.turn_id]: [...blocks, { kind: 'tool_use' as const, name: delta.name, summary: delta.summary }],
    },
    order: ensureOrder(state, delta.turn_id),
  }
}

// Live assistant turns not yet present in the canonical transcript (in arrival order).
export function liveOnlyTurns(transcript: TranscriptTurn[], live: LiveState): TranscriptTurn[] {
  if (live.ended) return []
  const transcriptIds = new Set(transcript.map((t) => t.id))
  return live.order
    .filter((id) => !transcriptIds.has(id) && live.byId[id]?.length)
    .map((id) => ({
      id,
      role: 'assistant' as const,
      blocks: live.byId[id]!,
      at: '',
    }))
}

// Merge canonical transcript turns with accumulated live blocks. Transcript turns render
// as-is and are authoritative; live blocks for ids NOT yet in the transcript append as
// in-progress assistant bubbles (in arrival order, after the transcript).
export function mergeTurns(transcript: TranscriptTurn[], live: LiveState): TranscriptTurn[] {
  return [...transcript, ...liveOnlyTurns(transcript, live)]
}
