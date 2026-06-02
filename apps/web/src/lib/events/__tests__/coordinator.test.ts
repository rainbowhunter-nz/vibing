import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createCoordinator } from '../coordinator'
import type { Scope } from '../types'

// ---------------------------------------------------------------------------
// MockEventSource
// ---------------------------------------------------------------------------

type ReadyState = 0 | 1 | 2

class MockEventSource {
  static instances: MockEventSource[] = []

  readonly url: string
  readyState: ReadyState = 0 // CONNECTING

  onopen: (() => void) | null = null
  onerror: ((e: Event) => void) | null = null

  private listeners: Record<string, Set<EventListener>> = {}

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: EventListener) {
    if (!this.listeners[type]) this.listeners[type] = new Set()
    this.listeners[type].add(listener)
  }

  removeEventListener(type: string, listener: EventListener) {
    this.listeners[type]?.delete(listener)
  }

  /** Simulate server open */
  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }

  /** Simulate a named event (e.g. "invalidate") with JSON data */
  simulateEvent(type: string, data: unknown) {
    const e = Object.assign(new Event(type), { data: JSON.stringify(data) }) as MessageEvent
    this.listeners[type]?.forEach((l) => l(e))
  }

  /** Simulate an error (browser sets readyState back to CONNECTING for auto-reconnect) */
  simulateError() {
    this.readyState = 0 // CONNECTING — auto-reconnect in progress
    const e = new Event('error')
    this.onerror?.(e)
  }

  /** Simulate a fatal close (readyState = CLOSED) */
  simulateFatalError() {
    this.readyState = 2 // CLOSED
    const e = new Event('error')
    this.onerror?.(e)
  }

  close() {
    this.readyState = 2
  }
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('coordinator — single EventSource', () => {
  it('AC1: opens exactly ONE EventSource on connect()', () => {
    const coord = createCoordinator()
    coord.connect()
    expect(MockEventSource.instances).toHaveLength(1)
    coord.disconnect()
  })

  it('AC1: calling connect() twice does not open a second EventSource', () => {
    const coord = createCoordinator()
    coord.connect()
    coord.connect() // idempotent
    expect(MockEventSource.instances).toHaveLength(1)
    coord.disconnect()
  })
})

describe('coordinator — scope-based callbacks', () => {
  it('AC3/AC7: invalidate event for scope X invokes callbacks for X', () => {
    const coord = createCoordinator()
    coord.connect()
    const cb = vi.fn()
    coord.register('devcontainers', cb)

    const [es] = MockEventSource.instances
    es.simulateOpen()
    es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'devcontainers', ids: ['dc1'] })

    expect(cb).toHaveBeenCalledOnce()
    coord.disconnect()
  })

  it('AC3/AC7: invalidate event for scope X does NOT invoke callbacks for scope Y', () => {
    const coord = createCoordinator()
    coord.connect()
    const cbA = vi.fn()
    const cbB = vi.fn()
    coord.register('devcontainers', cbA)
    coord.register('agent_sessions', cbB)

    const [es] = MockEventSource.instances
    es.simulateOpen()
    es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'devcontainers', ids: [] })

    expect(cbA).toHaveBeenCalledOnce()
    expect(cbB).not.toHaveBeenCalled()
    coord.disconnect()
  })

  it('AC4: all 5 scopes are routable', () => {
    const coord = createCoordinator()
    coord.connect()
    const scopes: Scope[] = ['devcontainers', 'agent_sessions', 'inbox', 'approvals', 'runtime']
    const cbs = scopes.map((s) => {
      const cb = vi.fn()
      coord.register(s, cb)
      return cb
    })

    const [es] = MockEventSource.instances
    es.simulateOpen()
    for (const scope of scopes) {
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope, ids: [] })
    }

    cbs.forEach((cb) => expect(cb).toHaveBeenCalledOnce())
    coord.disconnect()
  })

  it('AC8: registered callback runs on invalidation — no page reload', () => {
    // Verify via fn.mock.calls (if page reloaded, the module would re-init and fn lost)
    const coord = createCoordinator()
    coord.connect()
    const cb = vi.fn()
    coord.register('inbox', cb)

    const [es] = MockEventSource.instances
    es.simulateOpen()
    es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: ['i1'] })

    // callback was called in-process — no reload occurred
    expect(cb).toHaveBeenCalledOnce()
    coord.disconnect()
  })

  it('unsubscribe stops further calls', () => {
    const coord = createCoordinator()
    coord.connect()
    const cb = vi.fn()
    const unsub = coord.register('approvals', cb)

    const [es] = MockEventSource.instances
    es.simulateOpen()
    es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'approvals', ids: [] })
    expect(cb).toHaveBeenCalledOnce()

    unsub()
    es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'approvals', ids: [] })
    expect(cb).toHaveBeenCalledOnce() // still just once
    coord.disconnect()
  })
})

describe('coordinator — health state', () => {
  it('AC5: health starts as disconnected, becomes connected on open', () => {
    const coord = createCoordinator()
    expect(coord.health).toBe('disconnected')
    coord.connect()
    expect(coord.health).toBe('reconnecting') // connecting state before open
    const [es] = MockEventSource.instances
    es.simulateOpen()
    expect(coord.health).toBe('connected')
    coord.disconnect()
  })

  it('AC5/AC6: health becomes reconnecting on transient error (readyState=CONNECTING)', () => {
    const coord = createCoordinator()
    coord.connect()
    const [es] = MockEventSource.instances
    es.simulateOpen()
    expect(coord.health).toBe('connected')

    es.simulateError() // readyState=0 (CONNECTING), browser auto-reconnects
    expect(coord.health).toBe('reconnecting')
    coord.disconnect()
  })

  it('AC5: health becomes disconnected on fatal error (readyState=CLOSED)', () => {
    const coord = createCoordinator()
    coord.connect()
    const [es] = MockEventSource.instances
    es.simulateOpen()
    es.simulateFatalError() // readyState=2 (CLOSED)
    expect(coord.health).toBe('disconnected')
    coord.disconnect()
  })

  it('AC6: transient error does NOT create a duplicate EventSource', () => {
    const coord = createCoordinator()
    coord.connect()
    const [es] = MockEventSource.instances
    es.simulateOpen()
    es.simulateError() // triggers onerror handler — browser auto-reconnects, we must not open a second

    // Still only 1 instance — native EventSource handles reconnect
    expect(MockEventSource.instances).toHaveLength(1)
    coord.disconnect()
  })
})
