import { describe, it, expect } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useInterventionAction } from '../useInterventionAction'
import { ApiError } from '../../api'

describe('useInterventionAction', () => {
  it('runs idle → submitting → awaiting on success', async () => {
    const { result } = renderHook(() => useInterventionAction('STALE_CODE'))
    expect(result.current.state.kind).toBe('idle')

    let resolve!: () => void
    const submit = () => new Promise<void>((r) => (resolve = r))
    act(() => {
      void result.current.run('go', submit)
    })
    expect(result.current.state).toEqual({ kind: 'submitting', tag: 'go' })

    await act(async () => {
      resolve()
    })
    expect(result.current.state.kind).toBe('awaiting')
  })

  it('maps the stale code to a stale state', async () => {
    const { result } = renderHook(() => useInterventionAction('STALE_CODE'))
    act(() => {
      void result.current.run('go', () => Promise.reject(new ApiError(409, 'STALE_CODE', 'x')))
    })
    await waitFor(() => expect(result.current.state.kind).toBe('stale'))
  })

  it('maps other errors to an error state', async () => {
    const { result } = renderHook(() => useInterventionAction('STALE_CODE'))
    act(() => {
      void result.current.run('go', () => Promise.reject(new Error('boom')))
    })
    await waitFor(() => expect(result.current.state.kind).toBe('error'))
  })
})
