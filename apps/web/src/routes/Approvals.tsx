import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <path d="m9 11 3 3L22 4" />
  </svg>
)

export function Approvals() {
  return (
    <>
      <PageHeader title="Approvals" crumbs="Pending" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="No pending approvals"
          helper="Actions Claude Code asks permission for will queue here for your decision."
        />
      </div>
    </>
  )
}
