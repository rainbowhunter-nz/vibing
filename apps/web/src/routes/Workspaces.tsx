import { useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { fetchWorkspaces, type Workspace } from '../lib/api'
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

type State =
  | { kind: 'loading' }
  | { kind: 'list'; items: Workspace[] }
  | { kind: 'error' }

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
  return `${n} ${n === 1 ? 'workspace' : 'workspaces'}`
}

const COLUMNS = 'grid grid-cols-[1fr_110px_100px_150px_80px]'

export function Workspaces() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetchWorkspaces()
      .then((data) => {
        if (!cancelled) setState({ kind: 'list', items: data.items })
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  const crumbs = state.kind === 'list' ? countLabel(state.items.length) : undefined

  return (
    <>
      <PageHeader title="Workspaces" crumbs={crumbs} />
      <div className="flex-1 overflow-auto">
        {state.kind === 'loading' && (
          <div className="flex h-full items-center justify-center p-8 text-[13px] text-text-muted">
            Loading workspaces…
          </div>
        )}

        {state.kind === 'error' && (
          <div className="flex h-full items-center justify-center p-8">
            <div className="max-w-[320px] text-center">
              <h2 className="mb-1.5 text-[15px] font-semibold text-text">Couldn't load workspaces</h2>
              <p className="text-[13px] text-text-muted">
                Check that the backend is running, then reload the page.
              </p>
            </div>
          </div>
        )}

        {state.kind === 'list' && state.items.length === 0 && (
          <EmptyState
            icon={folderIcon}
            title="No workspaces yet"
            helper="Workspaces will appear here once you add a local folder."
          />
        )}

        {state.kind === 'list' && state.items.length > 0 && (
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
            {state.items.map((workspace) => {
              const running = isRunning(workspace.status)
              return (
                <div
                  key={workspace.id}
                  className={cn(
                    COLUMNS,
                    'items-center border-b border-border px-4 py-3',
                    running ? 'border-l-[3px] border-l-ok' : 'pl-[19px]',
                  )}
                >
                  <span className="text-[13px] font-semibold text-text">{workspace.name}</span>
                  <span className="text-xs text-text-muted">Local folder</span>
                  <span>
                    <span
                      className={cn(
                        'rounded-full px-2 py-0.5 text-[11px] font-medium',
                        statusBadgeClass(workspace.status),
                      )}
                    >
                      {workspace.status}
                    </span>
                  </span>
                  <span className="text-xs text-text-muted">{formatRelativeTime(workspace.updated_at)}</span>
                  <div className="flex items-center justify-end gap-0.5">
                    <button
                      title="Start"
                      disabled
                      className="flex h-7 w-7 cursor-not-allowed items-center justify-center rounded-[5px] text-text-muted opacity-[0.4]"
                    >
                      {playIcon}
                    </button>
                    <button
                      title="Stop"
                      disabled
                      className="flex h-7 w-7 cursor-not-allowed items-center justify-center rounded-[5px] text-text-muted opacity-[0.4]"
                    >
                      {stopIcon}
                    </button>
                    <button
                      title="Delete"
                      className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-[5px] text-bad hover:bg-surface-muted"
                    >
                      {trashIcon}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}
