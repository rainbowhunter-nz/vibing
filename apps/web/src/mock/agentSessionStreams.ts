// Mock per-session SSE delta playback (ADR-0010, VIB-109/110). Plays scripted assistant
// text + tool_use deltas through the MockEventSource opened at a session's /stream URL,
// so the live chat is inspectable without a real Control Plane. Mirrors how the real
// per-session stream serializes turn-deltas (named `turn_delta` events, JSON data).
//
// Boundary (mock README): this is a UI inspection aid — it emits scripted deltas only,
// it does NOT simulate Runtime Event processing or projection logic.

import type { TurnDelta } from '../lib/api/types'
import { liveInstancesMatching } from './events'

// Scripted deltas per session id. Each entry lists the steps after run_started / before
// run_ended. Use the 'with-tool-use' session to see mixed text + tool_use cards live.
const SCRIPTS: Record<string, { turnId: string; steps: TurnDelta[] }> = {
  // Default script: token-by-token text only.
  default: {
    turnId: 'mock-live-turn',
    steps: ['Let', ' me', ' take', ' a', ' look', ' at', ' that', '.', ' Done!'].map((text) => ({
      kind: 'text' as const,
      turn_id: 'mock-live-turn',
      role: 'assistant' as const,
      text,
    })),
  },
  // Mixed text + tool_use cards, inspectable via the /mock route.
  'mock-tool-use-session': {
    turnId: 'mock-tool-turn',
    steps: [
      { kind: 'text' as const, turn_id: 'mock-tool-turn', role: 'assistant' as const, text: 'Let me check that.' },
      { kind: 'tool_use' as const, turn_id: 'mock-tool-turn', name: 'Bash', summary: 'cmd=ls' },
      { kind: 'text' as const, turn_id: 'mock-tool-turn', role: 'assistant' as const, text: ' Reading the file.' },
      { kind: 'tool_use' as const, turn_id: 'mock-tool-turn', name: 'Read', summary: 'path=/a/b.ts' },
      { kind: 'text' as const, turn_id: 'mock-tool-turn', role: 'assistant' as const, text: ' Done!' },
    ],
  },
}

function scriptFor(sessionId: string): { turnId: string; steps: TurnDelta[] } {
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

// Play a session's scripted deltas: run_started, then steps, then run_ended.
// Returns a cancel function. Deterministic when a synchronous `schedule` is provided.
export function playSessionStream(sessionId: string, opts: PlayOptions = {}): () => void {
  const { steps } = scriptFor(sessionId)
  const delay = opts.tokenDelayMs ?? 0
  const schedule = opts.schedule ?? defaultSchedule
  let cancelled = false

  deliver(sessionId, { kind: 'run_started' })

  const allSteps: TurnDelta[] = [...steps, { kind: 'run_ended' as const }]

  const step = (i: number) => {
    if (cancelled || i >= allSteps.length) return
    deliver(sessionId, allSteps[i])
    schedule(() => step(i + 1), delay)
  }
  step(0)

  return () => {
    cancelled = true
  }
}
