// Mock per-session SSE delta playback (ADR-0010, VIB-109). Plays scripted assistant
// text token-by-token through the MockEventSource opened at a session's /stream URL, so
// the live chat is inspectable without a real Control Plane. Mirrors how the real
// per-session stream serializes turn-deltas (named `turn_delta` events, JSON data).
//
// Boundary (mock README): this is a UI inspection aid — it emits scripted deltas only,
// it does NOT simulate Runtime Event processing or projection logic.

import type { TurnDelta } from '../lib/api/types'
import { liveInstancesMatching } from './events'

// Scripted token-by-token assistant text per session id (the seed conversations).
const SCRIPTS: Record<string, { turnId: string; tokens: string[] }> = {
  // Default script used for any session without a specific entry.
  default: {
    turnId: 'mock-live-turn',
    tokens: ['Let', ' me', ' take', ' a', ' look', ' at', ' that', '.', ' Done!'],
  },
}

function scriptFor(sessionId: string): { turnId: string; tokens: string[] } {
  return SCRIPTS[sessionId] ?? SCRIPTS.default
}

function streamUrlMatcher(sessionId: string): (url: string) => boolean {
  const needle = `/agent-sessions/${sessionId}/stream`
  return (url) => url.includes(needle)
}

function deliver(sessionId: string, delta: TurnDelta): void {
  const data = JSON.stringify(delta)
  for (const inst of liveInstancesMatching(streamUrlMatcher(sessionId))) {
    inst._deliver('turn_delta', data)
  }
}

export interface PlayOptions {
  // Milliseconds between tokens. 0 (default in tests) emits synchronously.
  tokenDelayMs?: number
  // Injectable scheduler so tests can drive playback deterministically (no wall-clock).
  schedule?: (fn: () => void, ms: number) => void
}

const defaultSchedule = (fn: () => void, ms: number) => {
  setTimeout(fn, ms)
}

// Play a session's scripted deltas: run_started, then text tokens, then run_ended.
// Returns a cancel function. Deterministic when a synchronous `schedule` is provided.
export function playSessionStream(sessionId: string, opts: PlayOptions = {}): () => void {
  const { turnId, tokens } = scriptFor(sessionId)
  const delay = opts.tokenDelayMs ?? 0
  const schedule = opts.schedule ?? defaultSchedule
  let cancelled = false

  deliver(sessionId, { kind: 'run_started' })

  const steps: TurnDelta[] = [
    ...tokens.map((text) => ({ kind: 'text' as const, turn_id: turnId, role: 'assistant' as const, text })),
    { kind: 'run_ended' as const },
  ]

  const step = (i: number) => {
    if (cancelled || i >= steps.length) return
    deliver(sessionId, steps[i])
    schedule(() => step(i + 1), delay)
  }
  step(0)

  return () => {
    cancelled = true
  }
}
