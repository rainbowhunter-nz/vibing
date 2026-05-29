import type { ReactNode } from 'react'
import type { QueryState } from '../lib/api'
import { LoadingState } from './LoadingState'
import { ErrorState } from './ErrorState'
import { loadError } from '../lib/copy'

interface QueryBoundaryProps<T> {
  state: QueryState<T>
  loading?: ReactNode
  error?: ReactNode
  children: (data: T) => ReactNode
}

export function QueryBoundary<T>({ state, loading, error, children }: QueryBoundaryProps<T>) {
  switch (state.kind) {
    case 'loading':
      return <>{loading ?? <LoadingState />}</>
    case 'error':
      return <>{error ?? <ErrorState {...loadError('this page')} />}</>
    case 'ready':
      return <>{children(state.data)}</>
  }
}
