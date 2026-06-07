import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { installMockEventSource, resetMockEvents, setStreamState } from '../events'
import { playSessionStream } from '../agentSessionStreams'
import type { TurnDelta } from '../../lib/api/types'

// Synchronous scheduler so playback is deterministic (no wall-clock dependency).
const syncSchedule = (fn: () => void) => fn()

describe('mock per-session SSE delta playback', () => {
  beforeEach(() => {
    installMockEventSource()
    resetMockEvents()
    setStreamState('connected')
  })
  afterEach(() => {
    resetMockEvents()
  })

  function openStream(sessionId: string): { received: TurnDelta[]; es: EventSource } {
    const received: TurnDelta[] = []
    const es = new EventSource(`/api/v1/devcontainers/dc-1/agent-sessions/${sessionId}/stream`)
    es.addEventListener('turn_delta', (e) => {
      received.push(JSON.parse((e as MessageEvent).data as string))
    })
    return { received, es }
  }

  it('plays run_started, text tokens, then run_ended to the matching session stream', async () => {
    const { received } = openStream('as-seed-0005')
    // Let the microtask-deferred open() run so readyState becomes OPEN.
    await Promise.resolve()

    playSessionStream('as-seed-0005', { schedule: syncSchedule })

    const kinds = received.map((d) => d.kind)
    expect(kinds[0]).toBe('run_started')
    expect(kinds[kinds.length - 1]).toBe('run_ended')
    const texts = received.filter((d) => d.kind === 'text')
    expect(texts.length).toBeGreaterThan(0)
    // All text deltas share one turn id (token-by-token into one assistant bubble).
    const ids = new Set(texts.map((d) => (d.kind === 'text' ? d.turn_id : '')))
    expect(ids.size).toBe(1)
  })

  it('mock-tool-use-session script includes tool_use deltas interleaved with text (AC5)', async () => {
    const { received } = openStream('mock-tool-use-session')
    await Promise.resolve()

    playSessionStream('mock-tool-use-session', { schedule: syncSchedule })

    const kinds = received.map((d) => d.kind)
    expect(kinds[0]).toBe('run_started')
    expect(kinds[kinds.length - 1]).toBe('run_ended')
    const toolDeltas = received.filter((d) => d.kind === 'tool_use')
    expect(toolDeltas.length).toBeGreaterThan(0)
    // tool_use deltas carry name + summary
    for (const d of toolDeltas) {
      expect(d).toHaveProperty('name')
      expect(d).toHaveProperty('summary')
    }
    // Text and tool_use interleave: kinds list contains both (not just text)
    expect(kinds).toContain('text')
    expect(kinds).toContain('tool_use')
  })

  it('only delivers to the stream of the matching session', async () => {
    const mine = openStream('as-seed-0005')
    const other = openStream('as-seed-0002')
    await Promise.resolve()

    playSessionStream('as-seed-0005', { schedule: syncSchedule })

    expect(mine.received.length).toBeGreaterThan(0)
    expect(other.received.length).toBe(0)
  })

  it('cancel stops further delivery', async () => {
    const { received } = openStream('as-seed-0005')
    await Promise.resolve()

    // Defer steps so we can cancel before they run.
    const pending: Array<() => void> = []
    const cancel = playSessionStream('as-seed-0005', {
      schedule: (fn) => {
        pending.push(fn)
      },
    })
    const afterStart = received.length // run_started + first step already delivered
    cancel()
    pending.forEach((fn) => fn()) // these should no-op after cancel
    expect(received.length).toBe(afterStart)
  })
})
