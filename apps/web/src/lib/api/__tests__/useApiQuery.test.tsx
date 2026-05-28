import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { ApiError } from '../client'
import { useApiQuery } from '../useApiQuery'

afterEach(() => vi.restoreAllMocks())

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useApiQuery', () => {
  it('starts in loading and transitions to ready', async () => {
    const fn = vi.fn().mockResolvedValue({ count: 1 })
    const { result } = renderHook(() => useApiQuery(fn, []))
    expect(result.current.state).toEqual({ kind: 'loading' })
    await waitFor(() =>
      expect(result.current.state).toEqual({ kind: 'ready', data: { count: 1 } }),
    )
  })

  it('transitions to error when the function rejects with ApiError', async () => {
    const err = new ApiError(404, 'NOT_FOUND', 'gone')
    const fn = vi.fn().mockRejectedValue(err)
    const { result } = renderHook(() => useApiQuery(fn, []))
    await waitFor(() => {
      expect(result.current.state).toEqual({ kind: 'error', error: err })
    })
  })

  it('refetch flips back to loading then resolves with the new value', async () => {
    let call = 0
    const fn = vi.fn().mockImplementation(() => Promise.resolve(++call))
    const { result } = renderHook(() => useApiQuery(fn, []))
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 1 }))
    act(() => result.current.refetch())
    expect(result.current.state).toEqual({ kind: 'loading' })
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 2 }))
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('unmount before resolution does not call setState', async () => {
    const d = deferred<string>()
    const fn = vi.fn().mockReturnValue(d.promise)
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { result, unmount } = renderHook(() => useApiQuery(fn, []))
    expect(result.current.state).toEqual({ kind: 'loading' })
    unmount()
    await act(async () => {
      d.resolve('late')
      // give the microtask queue a tick to flush
      await Promise.resolve()
    })
    expect(consoleError).not.toHaveBeenCalled()
  })
})
