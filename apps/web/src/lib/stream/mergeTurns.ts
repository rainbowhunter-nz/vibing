// Pure turn-merge reducer (ADR-0010, VIB-109): merges live text deltas with the
// canonical transcript, keyed by turn id. Partials accumulate in place (no duplicate
// or reordered bubbles); on the terminal run_ended the caller refetches the transcript
// and this merge reconciles by id — live text for ids now in the transcript is dropped
// in favor of the canonical turn. Text-only this slice (tool-call deltas are VIB-110).

import type { TextDelta, TranscriptTurn, TurnDelta } from '../api/types'

// Accumulated live text for the current run, keyed by turn id, preserving arrival order.
export interface LiveState {
  byId: Record<string, string>
  order: string[]
  // True once the run's terminal delta arrived; the view then reconciles to transcript.
  ended: boolean
}

export const emptyLiveState = (): LiveState => ({ byId: {}, order: [], ended: false })

// Fold one delta into the live state. Pure: returns a new state, never mutates.
export function liveReducer(state: LiveState, delta: TurnDelta): LiveState {
  switch (delta.kind) {
    case 'run_started':
      // A fresh run resets accumulated live text.
      return emptyLiveState()
    case 'run_ended':
      return { ...state, ended: true }
    case 'text':
      return appendText(state, delta)
  }
}

function appendText(state: LiveState, delta: TextDelta): LiveState {
  const existing = state.byId[delta.turn_id] ?? ''
  const order = delta.turn_id in state.byId ? state.order : [...state.order, delta.turn_id]
  return {
    ...state,
    byId: { ...state.byId, [delta.turn_id]: existing + delta.text },
    order,
  }
}

// Merge canonical transcript turns with accumulated live text. Transcript turns render
// as-is and are authoritative; live text for ids NOT yet in the transcript appends as
// in-progress assistant bubbles (in arrival order, after the transcript).
export function mergeTurns(transcript: TranscriptTurn[], live: LiveState): TranscriptTurn[] {
  const transcriptIds = new Set(transcript.map((t) => t.id))
  const liveOnly: TranscriptTurn[] = live.order
    .filter((id) => !transcriptIds.has(id) && live.byId[id])
    .map((id) => ({
      id,
      role: 'assistant' as const,
      blocks: [{ kind: 'text' as const, text: live.byId[id] }],
      at: '',
    }))
  return [...transcript, ...liveOnly]
}
