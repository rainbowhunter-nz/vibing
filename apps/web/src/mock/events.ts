import type { Scope } from '../lib/events/types'

export type StreamState = 'connected' | 'reconnecting' | 'disconnected'

// ---------------------------------------------------------------------------
// Stream-state store (same pattern as scenario.ts)
// ---------------------------------------------------------------------------

let streamState: StreamState = 'connected'
const stateListeners = new Set<() => void>()

export function getStreamState(): StreamState {
  return streamState
}

function notifyStateListeners() {
  stateListeners.forEach((fn) => fn())
}

export function subscribeStreamState(fn: () => void): () => void {
  stateListeners.add(fn)
  return () => stateListeners.delete(fn)
}

// ---------------------------------------------------------------------------
// Live instance registry
// ---------------------------------------------------------------------------

const liveInstances = new Set<MockEventSource>()

// ---------------------------------------------------------------------------
// MockEventSource — implements the EventSource surface consumed by coordinator
// ---------------------------------------------------------------------------

export class MockEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2

  readonly CONNECTING = 0
  readonly OPEN = 1
  readonly CLOSED = 2

  readonly url: string
  readyState: 0 | 1 | 2 = 0

  onopen: ((e: Event) => void) | null = null
  onerror: ((e: Event) => void) | null = null

  private _listeners: Record<string, Set<EventListener>> = {}

  constructor(url: string) {
    this.url = url
    liveInstances.add(this)

    // Simulate async connection (matches real EventSource behaviour)
    queueMicrotask(() => {
      if (this.readyState === 2) return // closed before open
      applyStateToInstance(this, streamState)
    })
  }

  addEventListener(type: string, listener: EventListener) {
    if (!this._listeners[type]) this._listeners[type] = new Set()
    this._listeners[type].add(listener)
  }

  removeEventListener(type: string, listener: EventListener) {
    this._listeners[type]?.delete(listener)
  }

  close() {
    this.readyState = 2
    liveInstances.delete(this)
  }

  // Internal: deliver a named event with string data
  _deliver(type: string, data: string) {
    if (this.readyState !== 1) return
    const e = Object.assign(new Event(type), { data }) as MessageEvent
    this._listeners[type]?.forEach((l) => l(e))
  }

  _open() {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }

  // Internal: simulate error (readyState drives reconnecting vs disconnected)
  _error(fatal: boolean) {
    this.readyState = fatal ? 2 : 0
    this.onerror?.(new Event('error'))
    if (fatal) liveInstances.delete(this)
  }
}

// ---------------------------------------------------------------------------
// Apply stream state to a single instance
// ---------------------------------------------------------------------------

function applyStateToInstance(inst: MockEventSource, state: StreamState) {
  if (inst.readyState === 2) return
  switch (state) {
    case 'connected':
      inst._open()
      break
    case 'reconnecting':
      inst._error(false)
      break
    case 'disconnected':
      inst._error(true)
      break
  }
}

// ---------------------------------------------------------------------------
// Controller: setStreamState + emit
// ---------------------------------------------------------------------------

export function setStreamState(state: StreamState) {
  streamState = state
  for (const inst of [...liveInstances]) {
    applyStateToInstance(inst, state)
  }
  notifyStateListeners()
}

export function emitInvalidation(scope: Scope) {
  const data = JSON.stringify({ event_type: 'invalidate', scope, ids: [] })
  for (const inst of [...liveInstances]) {
    inst._deliver('invalidate', data)
  }
}

// ---------------------------------------------------------------------------
// Install: swap global EventSource (call once before SseProvider mounts)
// ---------------------------------------------------------------------------

export function installMockEventSource() {
  globalThis.EventSource = MockEventSource as unknown as typeof EventSource
}

/** Reset module state (for tests) */
export function resetMockEvents() {
  liveInstances.clear()
  streamState = 'connected'
  notifyStateListeners()
}
