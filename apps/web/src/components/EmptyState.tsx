import type { ReactNode } from 'react'
import { StateMessage } from './StateMessage'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  helper: string
  action?: ReactNode
}

export function EmptyState(props: EmptyStateProps) {
  return <StateMessage {...props} tone="muted" />
}
