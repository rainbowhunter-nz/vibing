import { useCallback, useEffect, useState } from 'react'
import type { ApiError, NetworkError } from './client'

type QueryError = ApiError | NetworkError | Error

export type QueryState<T> =
  | { kind: 'loading' }
  | { kind: 'ready'; data: T; error?: QueryError }
  | { kind: 'error'; error: QueryError }

export interface QueryResult<T> {
  state: QueryState<T>
  isFetching: boolean
  refetch: () => void
}

export function useApiQuery<T>(fn: () => Promise<T>, deps: unknown[]): QueryResult<T> {
  const [state, setState] = useState<QueryState<T>>({ kind: 'loading' })
  const [isFetching, setIsFetching] = useState(true)
  const [refetchToken, setRefetchToken] = useState(0)

  // A deps change is a different resource: drop stale data back to loading.
  // A refetch (token bump) is the same resource: keep data visible (SWR).
  const [prevDeps, setPrevDeps] = useState(deps)
  if (deps.length !== prevDeps.length || deps.some((d, i) => !Object.is(d, prevDeps[i]))) {
    setPrevDeps(deps)
    setState({ kind: 'loading' })
    setIsFetching(true)
  }

  useEffect(() => {
    let cancelled = false
    fn().then(
      (data) => {
        if (cancelled) return
        setState({ kind: 'ready', data })
        setIsFetching(false)
      },
      (error: unknown) => {
        if (cancelled) return
        // Keep last-good data on a background refetch; full error only on first load.
        setState((prev) =>
          prev.kind === 'ready'
            ? { ...prev, error: error as QueryError }
            : { kind: 'error', error: error as QueryError },
        )
        setIsFetching(false)
      },
    )
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, refetchToken])

  const refetch = useCallback(() => {
    setIsFetching(true)
    setRefetchToken((n) => n + 1)
  }, [])

  return { state, isFetching, refetch }
}
