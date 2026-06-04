import { describe, it, expect, beforeEach } from 'vitest'
import {
  MockEventSource,
  emitInvalidation,
  setStreamState,
  getStreamState,
  installMockEventSource,
  resetMockEvents,
} from '../events'

// Flush microtask queue so queueMicrotask callbacks run synchronously in tests
async function flushMicrotasks() {
  await Promise.resolve()
}

beforeEach(() => {
  resetMockEvents()
})

describe('MockEventSource — construction and auto-open', () => {
  it('starts in CONNECTING state (readyState=0)', () => {
    const es = new MockEventSource('/api/v1/events')
    expect(es.readyState).toBe(0)
    es.close()
  })

  it('fires onopen and transitions to OPEN after microtask (stream connected)', async () => {
    const es = new MockEventSource('/api/v1/events')
    let opened = false
    es.onopen = () => { opened = true }
    await flushMicrotasks()
    expect(opened).toBe(true)
    expect(es.readyState).toBe(1)
    es.close()
  })

  it('does not fire onopen when stream is reconnecting', async () => {
    setStreamState('reconnecting')
    const es = new MockEventSource('/api/v1/events')
    let opened = false
    es.onopen = () => { opened = true }
    await flushMicrotasks()
    expect(opened).toBe(false)
    expect(es.readyState).toBe(0)
    es.close()
  })

  it('does not fire onopen when stream is disconnected; sets readyState=CLOSED', async () => {
    setStreamState('disconnected')
    const es = new MockEventSource('/api/v1/events')
    let opened = false
    es.onopen = () => { opened = true }
    await flushMicrotasks()
    expect(opened).toBe(false)
    expect(es.readyState).toBe(2)
  })
})

describe('MockEventSource — addEventListener and invalidate delivery', () => {
  it('delivers invalidate event to listener', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks() // open

    const received: unknown[] = []
    es.addEventListener('invalidate', (e) => received.push((e as MessageEvent).data))

    emitInvalidation('devcontainers')

    expect(received).toHaveLength(1)
    const parsed = JSON.parse(received[0] as string)
    expect(parsed).toEqual({ event_type: 'invalidate', scope: 'devcontainers', ids: [] })
    es.close()
  })

  it('does not deliver to a removed listener', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks()

    let count = 0
    const listener = () => { count++ }
    es.addEventListener('invalidate', listener)
    emitInvalidation('inbox')
    expect(count).toBe(1)

    es.removeEventListener('invalidate', listener)
    emitInvalidation('inbox')
    expect(count).toBe(1)
    es.close()
  })

  it('does not deliver when instance is CLOSED', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks()

    let count = 0
    es.addEventListener('invalidate', () => { count++ })
    es.close()
    emitInvalidation('approvals')
    expect(count).toBe(0)
  })

  it('delivers all 5 scopes', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks()

    const scopes: string[] = []
    es.addEventListener('invalidate', (e) => {
      scopes.push(JSON.parse((e as MessageEvent).data).scope as string)
    })

    const all = ['devcontainers', 'agent_sessions', 'inbox', 'approvals', 'runtime'] as const
    for (const s of all) emitInvalidation(s)

    expect(scopes).toEqual([...all])
    es.close()
  })
})

describe('MockEventSource — readyState', () => {
  it('readyState is 0 (CONNECTING) initially', () => {
    const es = new MockEventSource('/api/v1/events')
    expect(es.readyState).toBe(0)
    es.close()
  })

  it('readyState becomes 1 (OPEN) after auto-open', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks()
    expect(es.readyState).toBe(1)
    es.close()
  })

  it('readyState becomes 2 (CLOSED) after close()', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks()
    es.close()
    expect(es.readyState).toBe(2)
  })
})

describe('MockEventSource — onerror: reconnecting vs fatal', () => {
  it('setStreamState reconnecting → readyState=CONNECTING + onerror fires', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks()

    let errorFired = false
    es.onerror = () => { errorFired = true }

    setStreamState('reconnecting')

    expect(errorFired).toBe(true)
    expect(es.readyState).toBe(0) // CONNECTING — auto-reconnect
  })

  it('setStreamState disconnected → readyState=CLOSED + onerror fires', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks()

    let errorFired = false
    es.onerror = () => { errorFired = true }

    setStreamState('disconnected')

    expect(errorFired).toBe(true)
    expect(es.readyState).toBe(2) // CLOSED — fatal
  })
})

describe('MockEventSource — close removes from live set', () => {
  it('closed instance does not receive emits', async () => {
    const es1 = new MockEventSource('/api/v1/events')
    const es2 = new MockEventSource('/api/v1/events')
    await flushMicrotasks()

    let count1 = 0
    let count2 = 0
    es1.addEventListener('invalidate', () => { count1++ })
    es2.addEventListener('invalidate', () => { count2++ })

    es1.close()
    emitInvalidation('runtime')

    expect(count1).toBe(0)
    expect(count2).toBe(1)
    es2.close()
  })
})

describe('setStreamState connected — reconnect open', () => {
  it('fires onopen again when transitioning back to connected', async () => {
    const es = new MockEventSource('/api/v1/events')
    await flushMicrotasks()
    expect(es.readyState).toBe(1)

    setStreamState('reconnecting')
    expect(es.readyState).toBe(0)

    let reopened = false
    es.onopen = () => { reopened = true }
    setStreamState('connected')
    expect(reopened).toBe(true)
    expect(es.readyState).toBe(1)
    es.close()
  })
})

describe('installMockEventSource', () => {
  it('swaps global EventSource to MockEventSource', () => {
    const original = globalThis.EventSource
    installMockEventSource()
    expect(globalThis.EventSource).toBe(MockEventSource)
    // Restore
    globalThis.EventSource = original
  })
})

describe('getStreamState', () => {
  it('reflects current state', () => {
    expect(getStreamState()).toBe('connected')
    setStreamState('reconnecting')
    expect(getStreamState()).toBe('reconnecting')
    setStreamState('disconnected')
    expect(getStreamState()).toBe('disconnected')
  })
})
