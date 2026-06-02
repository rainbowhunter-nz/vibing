import { useCallback, useEffect, useState } from 'react'
import type { ApiError, NetworkError } from './client'

export type QueryState<T> =
  | { kind: 'loading' }
  | { kind: 'ready'; data: T }
  | { kind: 'error'; error: ApiError | NetworkError | Error }

export interface QueryResult<T> {
  state: QueryState<T>
  refetch: () => void
}

export function useApiQuery<T>(fn: () => Promise<T>, deps: unknown[]): QueryResult<T> {
  const [state, setState] = useState<QueryState<T>>({ kind: 'loading' })
  const [refetchToken, setRefetchToken] = useState(0)

  useEffect(() => {
    let cancelled = false
    fn().then(
      (data) => {
        if (!cancelled) setState({ kind: 'ready', data })
      },
      (error: unknown) => {
        if (!cancelled) setState({ kind: 'error', error: error as Error })
      },
    )
    return () => {
      cancelled = true
    }
    // deps come from the caller; refetchToken forces a re-run on refetch().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, refetchToken])

  const refetch = useCallback(() => {
    setState({ kind: 'loading' })
    setRefetchToken((n) => n + 1)
  }, [])

  return { state, refetch }
}
