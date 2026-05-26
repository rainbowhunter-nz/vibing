import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  helper: string
}

export function EmptyState({ icon, title, helper }: EmptyStateProps) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-[320px] text-center">
        <div aria-hidden="true" className="mx-auto mb-3.5 flex h-10 w-10 items-center justify-center rounded-[10px] bg-surface-muted text-accent">
          {icon}
        </div>
        <h2 className="mb-1.5 text-[15px] font-semibold text-text">{title}</h2>
        <p className="text-[13px] text-text-muted">{helper}</p>
      </div>
    </div>
  )
}
