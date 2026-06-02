import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  crumbs?: string
  action?: ReactNode
}

export function PageHeader({ title, crumbs, action }: PageHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-border px-6 py-3.5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text">{title}</h1>
        {crumbs && <div className="mt-0.5 text-[11px] text-text-muted">{crumbs}</div>}
      </div>
      {action}
    </header>
  )
}
