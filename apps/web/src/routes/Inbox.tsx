import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
  </svg>
)

export function Inbox() {
  return (
    <>
      <PageHeader title="Inbox" crumbs="All devcontainers" />
      <div className="flex-1 overflow-auto">
        <EmptyState
          icon={icon}
          title="Inbox is empty"
          helper="Questions, approval requests, failures and completions from your agent sessions will appear here."
        />
      </div>
    </>
  )
}
