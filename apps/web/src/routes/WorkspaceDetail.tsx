import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <path d="M12 18h.01" />
    <path d="M12 11v3" />
  </svg>
)

export function WorkspaceDetail() {
  return (
    <>
      <PageHeader title="Workspace" crumbs="Detail" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="Workspace not found"
          helper="This workspace doesn't exist or hasn't been created yet."
        />
      </div>
    </>
  )
}
