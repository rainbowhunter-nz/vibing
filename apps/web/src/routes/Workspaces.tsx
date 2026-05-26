import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
)

export function Workspaces() {
  return (
    <>
      <PageHeader title="Workspaces" crumbs="0 workspaces" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="No workspaces yet"
          helper="Your isolated development environments will appear here."
        />
      </div>
    </>
  )
}
