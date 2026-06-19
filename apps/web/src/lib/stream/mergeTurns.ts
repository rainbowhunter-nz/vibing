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

function pendingLiveTurns(
  transcript: TranscriptTurn[],
  live: LiveState,
): TranscriptTurn[] {
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

function sameBlocks(a: TranscriptBlock[], b: TranscriptBlock[]): boolean {
  if (a.length !== b.length) return false
  return a.every((blk, i) => {
    const other = b[i]
    if (blk.kind === 'text' && other.kind === 'text') return blk.text === other.text
    if (blk.kind === 'tool_use' && other.kind === 'tool_use')
      return blk.name === other.name && blk.summary === other.summary
    return false
  })
}

// A streamed turn is reconciled once the canonical transcript carries an assistant turn with
// the same blocks. The canonical turn lands under a DIFFERENT id than the streamed one (the
// stream uses Claude's message.id, the transcript its per-line uuid), so we match by content,
// not id. This is the single source of truth for dropping a live bubble — holding it until the
// canonical turn actually lands avoids the flicker where the reply vanishes during the
// transcript-refetch window, and content-matching avoids a duplicate once it does.
function isReconciled(liveTurn: TranscriptTurn, transcript: TranscriptTurn[]): boolean {
  return transcript.some((t) => t.role === 'assistant' && sameBlocks(t.blocks, liveTurn.blocks))
}

// Live assistant turns not yet reconciled into the canonical transcript (in arrival order).
// While streaming, every pending turn shows. After run_ended, a turn is held until its content
// lands in the transcript, then dropped in favour of the canonical turn.
export function liveOnlyTurns(transcript: TranscriptTurn[], live: LiveState): TranscriptTurn[] {
  const pending = pendingLiveTurns(transcript, live)
  if (!live.ended) return pending
  return pending.filter((t) => !isReconciled(t, transcript))
}

// Merge canonical transcript turns with accumulated live blocks. Transcript turns render
// as-is and are authoritative; live blocks not yet reconciled append as in-progress assistant
// bubbles (in arrival order, after the transcript).
export function mergeTurns(transcript: TranscriptTurn[], live: LiveState): TranscriptTurn[] {
  return [...transcript, ...liveOnlyTurns(transcript, live)]
}
