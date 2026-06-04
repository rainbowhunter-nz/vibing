import { useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import {
  listApprovalRequests,
  resolveAgentSessionApproval,
  ApiError,
  useApiQuery,
  type ApprovalRequest,
  type ApprovalResolution,
  type ApprovalStatus,
} from '../lib/api'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { formatRelativeTime } from '../lib/time'
import { cn } from '../lib/cn'

const icon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <path d="m9 11 3 3L22 4" />
  </svg>
)

const TABS: { status: ApprovalStatus; label: string }[] = [
  { status: 'pending', label: 'Pending' },
  { status: 'approved', label: 'Approved' },
  { status: 'rejected', label: 'Rejected' },
]

const EMPTY: Record<ApprovalStatus, { title: string; helper: string }> = {
  pending: {
    title: 'No pending approvals',
    helper: 'Actions Claude Code asks permission for queue here for your decision.',
  },
  approved: { title: 'No approved requests yet', helper: 'Requests you approve appear here.' },
  rejected: { title: 'No rejected requests', helper: 'Requests you reject appear here.' },
}

function badgeClass(status: ApprovalStatus): string {
  switch (status) {
    case 'pending':
      return 'bg-amber-100 text-amber-800'
    case 'approved':
      return 'bg-green-100 text-ok'
    case 'rejected':
      return 'bg-red-100 text-bad'
  }
}

function Tab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-md px-2.5 py-1 text-xs font-semibold',
        active ? 'bg-accent-bg text-accent' : 'text-text-muted hover:bg-surface-muted',
      )}
    >
      {label}
    </button>
  )
}

type ActionState =
  | { kind: 'idle' }
  | { kind: 'submitting'; resolution: ApprovalResolution }
  | { kind: 'awaiting' }
  | { kind: 'stale' }
  | { kind: 'error'; message: string }

function ActionButton({
  label,
  onClick,
  disabled,
  variant,
}: {
  label: string
  onClick: () => void
  disabled: boolean
  variant: 'approve' | 'reject'
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-md px-3 py-1 text-[12px] font-semibold disabled:opacity-40',
        variant === 'approve' ? 'bg-ok text-white' : 'border border-bad text-bad',
      )}
    >
      {label}
    </button>
  )
}

function ApprovalRow({ request }: { request: ApprovalRequest }) {
  const [action, setAction] = useState<ActionState>({ kind: 'idle' })

  async function resolve(resolution: ApprovalResolution) {
    setAction({ kind: 'submitting', resolution })
    try {
      await resolveAgentSessionApproval(request.devcontainer_id, request.agent_session_id, {
        approval_request_id: request.id,
        resolution,
      })
      setAction({ kind: 'awaiting' })
    } catch (err) {
      if (err instanceof ApiError && err.code === 'APPROVAL_REQUEST_NOT_PENDING') {
        setAction({ kind: 'stale' })
      } else {
        setAction({ kind: 'error', message: "Couldn't submit — try again." })
      }
    }
  }

  const submitting = action.kind === 'submitting'
  const showActions =
    request.status === 'pending' && action.kind !== 'awaiting' && action.kind !== 'stale'

  return (
    <div className="flex items-center gap-3 border-b border-border px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="truncate font-mono text-[12.5px] font-semibold text-text">{request.requested_action}</div>
        <div className="mt-0.5 text-[11px] text-text-muted">
          {request.devcontainer_id} · session {request.agent_session_id.slice(0, 8)} ·{' '}
          {formatRelativeTime(request.created_at)}
          {action.kind === 'awaiting' && <span className="text-accent"> · submitted · awaiting runtime</span>}
        </div>
        {action.kind === 'stale' && (
          <div className="mt-1 text-[11px] text-bad">Already resolved elsewhere — no longer pending.</div>
        )}
        {action.kind === 'error' && <div className="mt-1 text-[11px] text-bad">{action.message}</div>}
      </div>
      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', badgeClass(request.status))}>
        {request.status}
      </span>
      {showActions && (
        <div className="flex shrink-0 gap-2">
          <ActionButton
            label={action.kind === 'submitting' && action.resolution === 'approved' ? 'Approving…' : 'Approve'}
            onClick={() => resolve('approved')}
            disabled={submitting}
            variant="approve"
          />
          <ActionButton
            label={action.kind === 'submitting' && action.resolution === 'rejected' ? 'Rejecting…' : 'Reject'}
            onClick={() => resolve('rejected')}
            disabled={submitting}
            variant="reject"
          />
        </div>
      )}
    </div>
  )
}

export function Approvals() {
  const [status, setStatus] = useState<ApprovalStatus>('pending')
  const { state, refetch } = useApiQuery(() => listApprovalRequests({ status }), [status])
  const { register } = useSseInvalidation()

  useEffect(() => register('approvals', refetch), [register, refetch])
  useEffect(() => register('inbox', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetch), [register, refetch])

  const crumbs = state.kind === 'ready' ? `${state.data.items.length} ${status}` : undefined

  return (
    <>
      <PageHeader title="Approvals" crumbs={crumbs} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex gap-1.5 border-b border-border px-4 py-2.5">
          {TABS.map((t) => (
            <Tab key={t.status} label={t.label} active={status === t.status} onClick={() => setStatus(t.status)} />
          ))}
        </div>
        <div className="flex-1 overflow-auto">
          <QueryBoundary state={state} error={<ErrorState {...loadError('approvals')} />}>
            {(data) =>
              data.items.length === 0 ? (
                <EmptyState icon={icon} title={EMPTY[status].title} helper={EMPTY[status].helper} />
              ) : (
                <div>
                  {data.items.map((r) => (
                    <ApprovalRow key={r.id} request={r} />
                  ))}
                </div>
              )
            }
          </QueryBoundary>
        </div>
      </div>
    </>
  )
}
