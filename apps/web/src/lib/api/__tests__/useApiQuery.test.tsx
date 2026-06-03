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

  it('same-query refetch keeps current data visible and exposes isFetching', async () => {
    const first = deferred<number>()
    const second = deferred<number>()
    const fn = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { result } = renderHook(() => useApiQuery(fn, []))

    await act(async () => first.resolve(1))
    expect(result.current.state).toEqual({ kind: 'ready', data: 1 })
    expect(result.current.isFetching).toBe(false)

    act(() => result.current.refetch())
    // SWR: stays on last-good data, never flips to loading
    expect(result.current.state).toEqual({ kind: 'ready', data: 1 })
    expect(result.current.isFetching).toBe(true)

    await act(async () => second.resolve(2))
    expect(result.current.state).toEqual({ kind: 'ready', data: 2 })
    expect(result.current.isFetching).toBe(false)
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('repeated refetch increments fn call count and resolves to latest value', async () => {
    let call = 0
    const fn = vi.fn().mockImplementation(() => Promise.resolve(++call))
    const { result } = renderHook(() => useApiQuery(fn, []))
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 1 }))
    act(() => result.current.refetch())
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 2 }))
    act(() => result.current.refetch())
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 3 }))
    expect(fn).toHaveBeenCalledTimes(3)
  })

  it('error during a background refetch keeps last-good data and attaches the error', async () => {
    const err = new ApiError(500, 'SERVER_ERROR', 'boom')
    let call = 0
    const fn = vi.fn().mockImplementation(() =>
      ++call === 1 ? Promise.resolve({ ok: true }) : Promise.reject(err),
    )
    const { result } = renderHook(() => useApiQuery(fn, []))
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: { ok: true } }))
    act(() => result.current.refetch())
    await waitFor(() => expect(result.current.isFetching).toBe(false))
    expect(result.current.state).toEqual({ kind: 'ready', data: { ok: true }, error: err })
  })

  it('first-load error transitions to error (no data to keep)', async () => {
    const err = new ApiError(500, 'SERVER_ERROR', 'boom')
    const fn = vi.fn().mockRejectedValue(err)
    const { result } = renderHook(() => useApiQuery(fn, []))
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'error', error: err }))
  })

  it('a successful refetch clears a prior background error', async () => {
    const err = new ApiError(500, 'SERVER_ERROR', 'boom')
    let call = 0
    const fn = vi.fn().mockImplementation(() => {
      call += 1
      if (call === 2) return Promise.reject(err)
      return Promise.resolve(call)
    })
    const { result } = renderHook(() => useApiQuery(fn, []))
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 1 }))
    act(() => result.current.refetch())
    await waitFor(() =>
      expect(result.current.state).toEqual({ kind: 'ready', data: 1, error: err }),
    )
    act(() => result.current.refetch())
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 3 }))
  })

  it('a deps change still shows loading (different resource)', async () => {
    const fn = vi.fn().mockImplementation((id: string) => Promise.resolve(`data-${id}`))
    const { result, rerender } = renderHook(({ id }) => useApiQuery(() => fn(id), [id]), {
      initialProps: { id: 'a' },
    })
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 'data-a' }))
    rerender({ id: 'b' })
    expect(result.current.state).toEqual({ kind: 'loading' })
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 'data-b' }))
  })

  it('refetch has stable identity across re-renders', async () => {
    const fn = vi.fn().mockResolvedValue(42)
    const { result, rerender } = renderHook(() => useApiQuery(fn, []))
    await waitFor(() => expect(result.current.state).toEqual({ kind: 'ready', data: 42 }))
    const refetchBefore = result.current.refetch
    rerender()
    expect(result.current.refetch).toBe(refetchBefore)
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
