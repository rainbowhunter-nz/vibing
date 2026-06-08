// Tests for replay and reconnect behaviour via the mock (VIB-111).
//
// AC1: fresh EventSource receives buffered deltas with ids → state rebuilt correctly.
// AC2: reconnect from lastEventId resumes without gaps or duplicates.
// Uses MockEventSource + playSessionStream / deliverBuffered to mirror the real
// server's replay-on-connect behaviour without a live backend.

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { installMockEventSource, resetMockEvents, setStreamState } from '../../../mock/events'
import {
  playSessionStream,
  deliverBuffered,
  resetMockSessionStreams,
} from '../../../mock/agentSessionStreams'
import { liveInstancesMatching } from '../../../mock/events'
import { liveReducer, emptyLiveState } from '../mergeTurns'
import type { TurnDelta } from '../../api/types'

const syncSchedule = (fn: () => void) => fn()

function openStream(sessionId: string) {
  const received: Array<{ delta: TurnDelta; id: string }> = []
  const es = new EventSource(
    `/api/v1/devcontainers/dc-1/agent-sessions/${sessionId}/stream`,
  ) as unknown as ReturnType<typeof liveInstancesMatching>[number]
  es.addEventListener('turn_delta', (e) => {
    const msg = e as MessageEvent
    received.push({ delta: JSON.parse(msg.data as string) as TurnDelta, id: msg.lastEventId })
  })
  return { received, es }
}

describe('mock replay — AC1: page refresh replays full run', () => {
  beforeEach(() => {
    installMockEventSource()
    resetMockEvents()
    resetMockSessionStreams()
    setStreamState('connected')
  })
  afterEach(() => {
    resetMockEvents()
    resetMockSessionStreams()
  })

  it('fresh EventSource receives replayed deltas with monotonic ids', async () => {
    // Play partway through the stream (represents a mid-run scenario).
    playSessionStream('as-seed-0005', { schedule: syncSchedule })
    // At this point the run ended and buffer was evicted. Let's use a partial run instead.
    resetMockSessionStreams()

    // Simulate a partial run: publish a few items, then "refresh" (new EventSource).
    const sessionId = 'as-seed-0005'
    // We need to manually play to populate the buffer — use a deferred step scheme.
    const pending: Array<() => void> = []
    const cancel = playSessionStream(sessionId, {
      schedule: (fn) => pending.push(fn), // defer all steps after the first
    })

    // Now we have run_started in buffer. Simulate a page refresh.
    const { received } = openStream(sessionId)
    await Promise.resolve() // let microtask open the MockEventSource

    // "Server" replays buffered events to the new connection.
    const instances = liveInstancesMatching((url) => url.includes(`/agent-sessions/${sessionId}/stream`))
    expect(instances.length).toBe(1)
    deliverBuffered(sessionId, instances[0])

    // The replayed events have ids.
    expect(received.length).toBeGreaterThan(0)
    const ids = received.map((r) => r.id).filter(Boolean)
    expect(ids.length).toBe(received.length)
    // ids are monotonic integer strings
    const intIds = ids.map((id) => parseInt(id, 10))
    expect(intIds).toEqual([...intIds].sort((a, b) => a - b))

    // The live state rebuilt from replayed deltas includes the run_started delta.
    let state = emptyLiveState()
    for (const { delta } of received) state = liveReducer(state, delta)
    // run_started resets state; state after run_started is empty
    expect(state.ended).toBe(false)

    cancel()
    pending.length = 0
  })

  it('lastEventId is tracked per-delivered-event on MockEventSource', async () => {
    const sessionId = 'replay-id-test'
    const { es } = openStream(sessionId)
    await Promise.resolve()

    // Deliver events with explicit ids.
    es._deliver('turn_delta', JSON.stringify({ kind: 'text', turn_id: 't1', role: 'assistant', text: 'A' }), '1')
    es._deliver('turn_delta', JSON.stringify({ kind: 'text', turn_id: 't1', role: 'assistant', text: 'B' }), '2')

    expect(es.lastEventId).toBe('2')
  })
})

describe('mock reconnect — AC2: resume from lastEventId without gaps', () => {
  beforeEach(() => {
    installMockEventSource()
    resetMockEvents()
    resetMockSessionStreams()
    setStreamState('connected')
  })
  afterEach(() => {
    resetMockEvents()
    resetMockSessionStreams()
  })

  it('deliverBuffered with lastEventId skips already-received events', async () => {
    const sessionId = 'reconnect-test'
    const pending: Array<() => void> = []
    playSessionStream(sessionId, { schedule: (fn) => pending.push(fn) })
    // Buffer has run_started (id=1). Deliver one more step.
    pending.shift()?.() // deliver step[0] (first text token)
    // Buffer now has id=1 (run_started) and id=2 (first text).

    // First connection receives up to id=1 (only run_started).
    const { received: firstReceived, es: firstEs } = openStream(sessionId)
    await Promise.resolve()
    deliverBuffered(sessionId, firstEs, undefined) // replay all
    firstEs.close()

    expect(firstReceived.length).toBeGreaterThanOrEqual(1)
    const lastReceivedId = firstReceived[firstReceived.length - 1].id

    // Reconnect: new EventSource, replay only events after lastReceivedId.
    const { received: resumeReceived } = openStream(sessionId)
    await Promise.resolve()
    const newInstances = liveInstancesMatching(
      (url) => url.includes(`/agent-sessions/${sessionId}/stream`),
    )
    expect(newInstances.length).toBe(1)
    deliverBuffered(sessionId, newInstances[0], lastReceivedId)

    // None of the already-received ids should appear in the resumed events.
    const receivedIds = new Set(firstReceived.map((r) => r.id))
    for (const { id } of resumeReceived) {
      expect(receivedIds.has(id)).toBe(false)
    }
    // Resumed events have higher ids than what was already received.
    const afterInt = parseInt(lastReceivedId, 10)
    for (const { id } of resumeReceived) {
      expect(parseInt(id, 10)).toBeGreaterThan(afterInt)
    }

    pending.forEach((fn) => fn())
  })
})
