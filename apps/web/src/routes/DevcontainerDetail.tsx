import { useEffect } from 'react'
import { useParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { fetchDevcontainer, fetchAgentSessions, useApiQuery, ApiError, type Devcontainer } from '../lib/api'
import type { AgentSession } from '../lib/api/types'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-emerald-100 text-emerald-800'
    case 'starting':
    case 'stopping':
      return 'bg-accent-bg text-accent'
    case 'error':
      return 'bg-red-100 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function agentSessionBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-emerald-100 text-emerald-800'
    case 'starting':
    case 'waiting_for_approval':
      return 'bg-accent-bg text-accent'
    case 'failed':
      return 'bg-red-100 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 border-b border-border px-4 py-3">
      <span className="w-28 shrink-0 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">{label}</span>
      <span className="text-[13px] text-text">{children}</span>
    </div>
  )
}

function DevcontainerInfo({ dc }: { dc: Devcontainer }) {
  return (
    <div className="px-4 pt-4">
      <h2 className="mb-4 text-base font-semibold text-text">{dc.name}</h2>
      <div className="rounded-md border border-border">
        <Row label="Local path">{dc.local_path}</Row>
        <Row label="Status">
          <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', statusBadgeClass(dc.status))}>
            {dc.status}
          </span>
        </Row>
        <Row label="Created">{dc.created_at}</Row>
        <Row label="Updated">{dc.updated_at}</Row>
      </div>
    </div>
  )
}

function AgentSessionsList({ sessions }: { sessions: AgentSession[] }) {
  return (
    <div className="px-4 pt-6">
      <h3 className="mb-3 text-sm font-semibold text-text">Agent Sessions</h3>
      {sessions.length === 0 ? (
        <p className="text-[13px] text-text-muted">No agent sessions</p>
      ) : (
        <div className="rounded-md border border-border">
          {sessions.map((s) => (
            <div key={s.id} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
              <span className="font-mono text-[12px] text-text-muted">{s.id.slice(0, 8)}</span>
              <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', agentSessionBadgeClass(s.status))}>
                {s.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function errorElement(error: unknown) {
  if (error instanceof ApiError && error.code === 'DEVCONTAINER_NOT_FOUND') {
    return (
      <ErrorState
        title="Devcontainer not found"
        helper="This devcontainer doesn't exist or has been deleted."
      />
    )
  }
  return <ErrorState {...loadError('devcontainer')} />
}

export function DevcontainerDetail() {
  const { id } = useParams<{ id: string }>()
  const { register } = useSseInvalidation()

  const { state, refetch } = useApiQuery(() => fetchDevcontainer(id!), [id])
  const { state: sessionsState, refetch: refetchSessions } = useApiQuery(
    () => fetchAgentSessions(id!),
    [id],
  )

  useEffect(() => register('devcontainers', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetchSessions), [register, refetchSessions])

  return (
    <>
      <PageHeader title="Devcontainer" crumbs="Detail" />
      <div className="flex-1 overflow-auto">
        <QueryBoundary state={state} error={errorElement(state.kind === 'error' ? state.error : null)}>
          {(dc) => (
            <>
              <DevcontainerInfo dc={dc} />
              {sessionsState.kind === 'ready' && <AgentSessionsList sessions={sessionsState.data.items} />}
            </>
          )}
        </QueryBoundary>
      </div>
    </>
  )
}
