import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import React from 'react'
import { SseProvider } from '../SseProvider'
import { useSseInvalidation } from '../useSseInvalidation'


// ---------------------------------------------------------------------------
// MockEventSource (same pattern as coordinator tests)
// ---------------------------------------------------------------------------

class MockEventSource {
  static instances: MockEventSource[] = []

  readonly url: string
  readyState: 0 | 1 | 2 = 0

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

  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }

  simulateEvent(type: string, data: unknown) {
    const e = Object.assign(new Event(type), { data: JSON.stringify(data) }) as MessageEvent
    this.listeners[type]?.forEach((l) => l(e))
  }

  simulateError() {
    this.readyState = 0
    this.onerror?.(new Event('error'))
  }

  close() {
    this.readyState = 2
  }
}

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
  cleanup()
})

function wrapper({ children }: { children: React.ReactNode }) {
  return <SseProvider>{children}</SseProvider>
}

describe('useSseInvalidation via SseProvider', () => {
  it('AC1: mounts exactly one EventSource', () => {
    renderHook(() => useSseInvalidation(), { wrapper })
    expect(MockEventSource.instances).toHaveLength(1)
  })

  it('AC3: register callback fires on matching invalidation', async () => {
    const cb = vi.fn()
    const { result } = renderHook(() => useSseInvalidation(), { wrapper })

    act(() => {
      result.current.register('devcontainers', cb)
    })

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'devcontainers', ids: ['dc1'] })
    })

    expect(cb).toHaveBeenCalledOnce()
  })

  it('AC8: callback fires without page reload (in-process assertion)', () => {
    const cb = vi.fn()
    const { result } = renderHook(() => useSseInvalidation(), { wrapper })

    act(() => {
      result.current.register('inbox', cb)
    })
    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: [] })
    })

    // If page had reloaded, module state would be reset and cb would not appear called
    expect(cb).toHaveBeenCalledOnce()
  })

  it('unsubscribe from provider stops further calls', () => {
    const cb = vi.fn()
    const { result } = renderHook(() => useSseInvalidation(), { wrapper })

    let unsub!: () => void
    act(() => {
      unsub = result.current.register('approvals', cb)
    })

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'approvals', ids: [] })
    })
    expect(cb).toHaveBeenCalledOnce()

    act(() => { unsub() })

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'approvals', ids: [] })
    })
    expect(cb).toHaveBeenCalledOnce()
  })
})
