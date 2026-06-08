// Mock per-session SSE delta playback with replay support (ADR-0010, VIB-111).
// Plays scripted assistant text + tool_use deltas through the MockEventSource opened at
// a session's /stream URL, so the live chat is inspectable without a real Control Plane.
// Mirrors how the real per-session stream serializes turn-deltas (named `turn_delta`
// events, JSON data) and carries a monotonic integer `id` on each event.
//
// Replay support (VIB-111): the scripted buffer is kept in-memory per session.
// deliverBuffered(sessionId, es) replays the buffer to a freshly-opened EventSource,
// faithfully mirroring the real server's replay-on-connect behaviour. This makes
// AC1/AC2 inspectable + testable with the mock: a fresh instance connects → replays
// the buffer → continues live; a reconnect starting from lastEventId resumes mid-buffer.
//
// Boundary: scripted playback only — no Runtime Event simulation or projection logic.

import type { TranscriptBlock, TurnDelta } from '../lib/api/types'
import { emitInvalidation, liveInstancesMatching, type MockEventSource } from './events'
import { completeAgentSessionRun, NotFoundError } from './state/agentSessions'

// Scripted deltas per session id. Each entry lists the steps after run_started / before run_ended.
const SCRIPTS: Record<string, { turnId: string; steps: TurnDelta[] }> = {
  default: {
    turnId: 'mock-live-turn',
    steps: ['Let', ' me', ' take', ' a', ' look', ' at', ' that', '.', ' Done!'].map((text) => ({
      kind: 'text' as const,
      turn_id: 'mock-live-turn',
      role: 'assistant' as const,
      text,
    })),
  },
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

// In-memory replay buffer per session: list of {id, data} for the current run.
// Cleared on run_started, evicted on run_ended — mirrors the real registry lifecycle.
const _buffers: Record<string, Array<{ id: string; data: string }>> = {}
let _counters: Record<string, number> = {}

function scriptFor(sessionId: string): { turnId: string; steps: TurnDelta[] } {
  return SCRIPTS[sessionId] ?? SCRIPTS.default
}

function stepsToBlocks(steps: TurnDelta[]): TranscriptBlock[] {
  const blocks: TranscriptBlock[] = []
  let text = ''
  const flush = () => {
    if (text) {
      blocks.push({ kind: 'text', text })
      text = ''
    }
  }
  for (const step of steps) {
    if (step.kind === 'text') text += step.text
    else if (step.kind === 'tool_use') {
      flush()
      blocks.push({ kind: 'tool_use', name: step.name, summary: step.summary })
    }
  }
  flush()
  return blocks
}

function streamUrlMatcher(sessionId: string): (url: string) => boolean {
  const needle = `/agent-sessions/${sessionId}/stream`
  return (url) => url.includes(needle)
}

function deliverToInstances(sessionId: string, delta: TurnDelta, id: string): void {
  const data = JSON.stringify(delta)
  for (const inst of liveInstancesMatching(streamUrlMatcher(sessionId))) {
    inst._deliver('turn_delta', data, id)
  }
}

/** Replay buffered events to a single EventSource instance starting after lastEventId. */
export function deliverBuffered(sessionId: string, es: MockEventSource, lastEventId?: string): void {
  const buf = _buffers[sessionId] ?? []
  const after = lastEventId !== undefined ? parseInt(lastEventId, 10) : -1
  for (const entry of buf) {
    if (parseInt(entry.id, 10) > after) {
      es._deliver('turn_delta', entry.data, entry.id)
    }
  }
}

export interface PlayOptions {
  // Milliseconds between tokens. 0 (default in tests) emits synchronously.
  tokenDelayMs?: number
  // Injectable scheduler so tests can drive playback deterministically (no wall-clock).
  schedule?: (fn: () => void, ms: number) => void
  // When true (default), mark the session completed and persist transcript on run_ended.
  completeSession?: boolean
}

const defaultSchedule = (fn: () => void, ms: number) => {
  setTimeout(fn, ms)
}

// Play a session's scripted deltas: run_started, then steps, then run_ended.
// Each event is buffered (for replay on reconnect) and delivered with a monotonic id.
// Returns a cancel function. Deterministic when a synchronous `schedule` is provided.
export function playSessionStream(sessionId: string, opts: PlayOptions = {}): () => void {
  const script = scriptFor(sessionId)
  const { steps } = script
  const delay = opts.tokenDelayMs ?? 0
  const schedule = opts.schedule ?? defaultSchedule
  const completeSession = opts.completeSession ?? true
  let cancelled = false

  // Reset buffer and counter for this run (matches registry begin_run).
  _buffers[sessionId] = []
  _counters[sessionId] = 1

  const publish = (delta: TurnDelta): void => {
    const id = String(_counters[sessionId]++)
    const data = JSON.stringify(delta)
    _buffers[sessionId].push({ id, data })
    deliverToInstances(sessionId, delta, id)
  }

  publish({ kind: 'run_started' })

  const allSteps: TurnDelta[] = [...steps, { kind: 'run_ended' as const }]

  const step = (i: number) => {
    if (cancelled || i >= allSteps.length) return
    const delta = allSteps[i]
    publish(delta)
    // Evict buffer on run_ended (matches registry end_run).
    if (delta.kind === 'run_ended') {
      delete _buffers[sessionId]
      delete _counters[sessionId]
      if (completeSession) {
        try {
          completeAgentSessionRun(sessionId, {
            id: script.turnId,
            blocks: stepsToBlocks(steps),
          })
          emitInvalidation('agent_sessions')
        } catch (e) {
          if (!(e instanceof NotFoundError)) throw e
        }
      }
    }
    schedule(() => step(i + 1), delay)
  }
  step(0)

  return () => {
    cancelled = true
  }
}

/** Reset all mock buffer state (for tests). */
export function resetMockSessionStreams(): void {
  for (const key of Object.keys(_buffers)) delete _buffers[key]
  _counters = {}
}
