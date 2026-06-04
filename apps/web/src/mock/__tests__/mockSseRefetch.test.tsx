/**
 * AC5: Proves that a manual emitInvalidation triggers the existing SWR refetch path.
 *
 * The test installs MockEventSource as the global, mounts SseProvider + a component
 * that registers a devcontainers invalidation callback via useSseInvalidation, then
 * calls emitInvalidation and asserts the callback was invoked.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import React from 'react'
import { MockEventSource, emitInvalidation, installMockEventSource, resetMockEvents } from '../events'
import { SseProvider } from '../../lib/events/SseProvider'
import { useSseInvalidation } from '../../lib/events/useSseInvalidation'

function wrapper({ children }: { children: React.ReactNode }) {
  return <SseProvider>{children}</SseProvider>
}

beforeEach(async () => {
  resetMockEvents()
  installMockEventSource()
  // flush queueMicrotask after each render
})

afterEach(() => {
  vi.unstubAllGlobals()
  cleanup()
})

describe('AC5: manual emitInvalidation triggers refetch callback via coordinator', () => {
  it('devcontainers invalidation reaches a registered callback', async () => {
    const cb = vi.fn()
    const { result } = renderHook(() => useSseInvalidation(), { wrapper })

    // Register a callback (simulates what Devcontainers route does)
    act(() => {
      result.current.register('devcontainers', cb)
    })

    // Let the auto-open microtask fire so the instance is OPEN
    await act(async () => {
      await Promise.resolve()
    })

    // Now emit — should reach coordinator → callback
    act(() => {
      emitInvalidation('devcontainers')
    })

    expect(cb).toHaveBeenCalledOnce()
    expect(cb).toHaveBeenCalledWith({ event_type: 'invalidate', scope: 'devcontainers', ids: [] })
  })

  it('all 5 scopes route to the correct callbacks', async () => {
    const cbs = {
      devcontainers: vi.fn(),
      agent_sessions: vi.fn(),
      inbox: vi.fn(),
      approvals: vi.fn(),
      runtime: vi.fn(),
    } as const

    const { result } = renderHook(() => useSseInvalidation(), { wrapper })

    act(() => {
      for (const [scope, cb] of Object.entries(cbs)) {
        result.current.register(scope as keyof typeof cbs, cb)
      }
    })

    await act(async () => { await Promise.resolve() })

    act(() => {
      for (const scope of Object.keys(cbs) as Array<keyof typeof cbs>) {
        emitInvalidation(scope)
      }
    })

    for (const cb of Object.values(cbs)) {
      expect(cb).toHaveBeenCalledOnce()
    }
  })

  it('uses MockEventSource as the global after installMockEventSource', () => {
    expect(globalThis.EventSource).toBe(MockEventSource)
  })
})
