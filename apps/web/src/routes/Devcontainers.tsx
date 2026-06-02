import { useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import {
  fetchDevcontainers,
  startDevcontainer,
  stopDevcontainer,
  deleteDevcontainer,
  useApiQuery,
  type Devcontainer,
} from '../lib/api'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'

const folderIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
)

const playIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="5 3 19 12 5 21 5 3" />
  </svg>
)

const stopIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" />
  </svg>
)

const trashIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
)

const spinnerIcon = (
  <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-border border-t-accent" />
)

const RUNNING_STATUSES = new Set(['running', 'starting', 'stopping'])

function isRunning(status: string): boolean {
  return RUNNING_STATUSES.has(status)
}

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

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 60 * 60 * 24 * 365],
  ['month', 60 * 60 * 24 * 30],
  ['day', 60 * 60 * 24],
  ['hour', 60 * 60],
  ['minute', 60],
  ['second', 1],
]

const relativeTimeFormat = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

function formatRelativeTime(iso: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000)
  const abs = Math.abs(seconds)
  for (const [unit, secondsPerUnit] of RELATIVE_UNITS) {
    if (abs >= secondsPerUnit || unit === 'second') {
      return relativeTimeFormat.format(Math.round(seconds / secondsPerUnit), unit)
    }
  }
  return relativeTimeFormat.format(0, 'second')
}

function countLabel(n: number): string {
  return `${n} ${n === 1 ? 'devcontainer' : 'devcontainers'}`
}

const COLUMNS = 'grid grid-cols-[1fr_110px_100px_150px_80px]'

type PendingAction = { id: string; action: 'start' | 'stop' | 'delete' }

function DevcontainerTable({
  items,
  pending,
  onStart,
  onStop,
  onDelete,
}: {
  items: Devcontainer[]
  pending: PendingAction | null
  onStart: (id: string) => void
  onStop: (id: string) => void
  onDelete: (id: string) => void
}) {
  return (
    <div>
      <div
        className={cn(
          COLUMNS,
          'border-b border-border bg-surface-muted px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted',
        )}
      >
        <span>Name</span>
        <span>Source</span>
        <span>Status</span>
        <span>Last Updated</span>
        <span />
      </div>
      {items.map((devcontainer) => {
        const running = isRunning(devcontainer.status)
        const isBusy = pending?.id === devcontainer.id
        const canStart = !running
        const canStop = devcontainer.status === 'running'

        return (
          <div
            key={devcontainer.id}
            className={cn(
              COLUMNS,
              'items-center border-b border-border px-4 py-3',
              running ? 'border-l-[3px] border-l-ok' : 'pl-[19px]',
            )}
          >
            <span className="text-[13px] font-semibold text-text">{devcontainer.name}</span>
            <span className="text-xs text-text-muted">Local folder</span>
            <span>
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-[11px] font-medium',
                  statusBadgeClass(devcontainer.status),
                )}
              >
                {devcontainer.status}
              </span>
            </span>
            <span className="text-xs text-text-muted">{formatRelativeTime(devcontainer.updated_at)}</span>
            <div className="flex items-center justify-end gap-0.5">
              <button
                title="Start"
                disabled={isBusy || !canStart}
                onClick={() => onStart(devcontainer.id)}
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded-[5px]',
                  isBusy || !canStart
                    ? 'cursor-not-allowed text-text-muted opacity-[0.4]'
                    : 'cursor-pointer text-text-muted hover:bg-surface-muted',
                )}
              >
                {isBusy && pending?.action === 'start' ? spinnerIcon : playIcon}
              </button>
              <button
                title="Stop"
                disabled={isBusy || !canStop}
                onClick={() => onStop(devcontainer.id)}
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded-[5px]',
                  isBusy || !canStop
                    ? 'cursor-not-allowed text-text-muted opacity-[0.4]'
                    : 'cursor-pointer text-text-muted hover:bg-surface-muted',
                )}
              >
                {isBusy && pending?.action === 'stop' ? spinnerIcon : stopIcon}
              </button>
              <button
                title="Delete"
                disabled={isBusy}
                onClick={() => onDelete(devcontainer.id)}
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded-[5px]',
                  isBusy
                    ? 'cursor-not-allowed text-bad opacity-[0.4]'
                    : 'cursor-pointer text-bad hover:bg-surface-muted',
                )}
              >
                {isBusy && pending?.action === 'delete' ? spinnerIcon : trashIcon}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function Devcontainers() {
  const { state, refetch } = useApiQuery(fetchDevcontainers, [])
  const { register } = useSseInvalidation()
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => register('devcontainers', refetch), [register, refetch])
  const crumbs = state.kind === 'ready' ? countLabel(state.data.items.length) : undefined

  async function handleAction(id: string, action: PendingAction['action'], fn: () => Promise<unknown>) {
    setPending({ id, action })
    setActionError(null)
    try {
      await fn()
      refetch()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(null)
    }
  }

  return (
    <>
      <PageHeader title="Devcontainers" crumbs={crumbs} />
      <div className="flex-1 overflow-auto">
        {actionError && (
          <div className="px-4 pt-3">
            <ErrorState title="Action failed" helper={actionError} />
          </div>
        )}
        <QueryBoundary state={state} error={<ErrorState {...loadError('devcontainers')} />}>
          {(data) =>
            data.items.length === 0 ? (
              <EmptyState
                icon={folderIcon}
                title="No devcontainers yet"
                helper="Devcontainers will appear here once you add a local folder."
              />
            ) : (
              <DevcontainerTable
                items={data.items}
                pending={pending}
                onStart={(id) => handleAction(id, 'start', () => startDevcontainer(id))}
                onStop={(id) => handleAction(id, 'stop', () => stopDevcontainer(id))}
                onDelete={(id) => handleAction(id, 'delete', () => deleteDevcontainer(id))}
              />
            )
          }
        </QueryBoundary>
      </div>
    </>
  )
}
