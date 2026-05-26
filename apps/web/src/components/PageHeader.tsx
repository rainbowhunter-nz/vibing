interface PageHeaderProps {
  title: string
  crumbs?: string
}

export function PageHeader({ title, crumbs }: PageHeaderProps) {
  return (
    <header className="border-b border-border px-6 py-3.5">
      <h1 className="text-lg font-semibold tracking-tight text-text">{title}</h1>
      {crumbs && <div className="mt-0.5 text-[11px] text-text-muted">{crumbs}</div>}
    </header>
  )
}
