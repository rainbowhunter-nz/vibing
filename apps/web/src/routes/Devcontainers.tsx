import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { DevcontainerFormModal } from '../components/DevcontainerFormModal'
import {
  fetchDevcontainerViews,
  startDevcontainer,
  stopDevcontainer,
  deleteDevcontainer,
  useApiQuery,
  type Devcontainer,
  type DevcontainerView,
} from '../lib/api'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'
import { formatRelativeTime } from '../lib/time'
import { PlayIcon, StopIcon, TrashIcon, SpinnerIcon } from '../components/icons'

const folderIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
)

const editIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
)

const RUNNING_STATUSES = new Set(['running', 'starting', 'stopping'])

function isRunning(status: string): boolean {
  return RUNNING_STATUSES.has(status)
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-accent/15 text-accent'
    case 'starting':
    case 'stopping':
      return 'bg-accent/15 text-accent'
    case 'error':
      return 'bg-bad/15 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
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
  onEdit,
}: {
  items: DevcontainerView[]
  pending: PendingAction | null
  onStart: (id: string) => void
  onStop: (id: string) => void
  onDelete: (id: string) => void
  onEdit: (devcontainer: Devcontainer) => void
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
            <Link
              to={`/devcontainers/${devcontainer.id}`}
              className="text-[13px] font-semibold text-text hover:text-accent hover:underline"
            >
              {devcontainer.name}
            </Link>
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
            <span className="text-xs text-text-muted">
              {devcontainer.updated_at ? formatRelativeTime(devcontainer.updated_at) : '—'}
              {devcontainer.runtime.runtime_connected && (
                <span title="Runtime connected" className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-ok align-middle" />
              )}
            </span>
            <div className="flex items-center justify-end gap-0.5">
              <button
                title="Edit"
                disabled={isBusy}
                onClick={() => onEdit(devcontainer)}
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded-[5px]',
                  isBusy
                    ? 'cursor-not-allowed text-text-muted opacity-[0.4]'
                    : 'cursor-pointer text-text-muted hover:bg-surface-muted',
                )}
              >
                {editIcon}
              </button>
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
                {isBusy && pending?.action === 'start' ? <SpinnerIcon /> : <PlayIcon />}
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
                {isBusy && pending?.action === 'stop' ? <SpinnerIcon /> : <StopIcon />}
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
                {isBusy && pending?.action === 'delete' ? <SpinnerIcon /> : <TrashIcon />}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function Devcontainers() {
  const { state, refetch } = useApiQuery(fetchDevcontainerViews, [])
  const { register } = useSseInvalidation()
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [modal, setModal] = useState<{ mode: 'create' } | { mode: 'edit'; dc: Devcontainer } | null>(null)

  useEffect(() => register('devcontainers', refetch), [register, refetch])
  useEffect(() => register('runtime', refetch), [register, refetch])
  const crumbs = state.kind === 'ready' ? countLabel(state.data.items.length) : undefined
  const refreshError = state.kind === 'ready' ? state.error : undefined

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

  const addButton = (
    <button
      onClick={() => setModal({ mode: 'create' })}
      className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-bg"
    >
      + Add
    </button>
  )

  return (
    <>
      <PageHeader title="Devcontainers" crumbs={crumbs} action={addButton} />
      <div className="flex-1 overflow-auto">
        {actionError && (
          <div className="px-4 pt-3">
            <ErrorState title="Action failed" helper={actionError} />
          </div>
        )}
        {refreshError && (
          <div className="px-4 pt-3">
            <ErrorState title="Couldn't refresh" helper={refreshError.message} />
          </div>
        )}
        <QueryBoundary state={state} error={<ErrorState {...loadError('devcontainers')} />}>
          {(data) =>
            data.items.length === 0 ? (
              <EmptyState
                icon={folderIcon}
                title="No devcontainers yet"
                helper="Add a local folder to get started."
                action={
                  <button
                    onClick={() => setModal({ mode: 'create' })}
                    className="rounded-md bg-accent px-3.5 py-2 text-xs font-semibold text-bg"
                  >
                    Add devcontainer
                  </button>
                }
              />
            ) : (
              <DevcontainerTable
                items={data.items}
                pending={pending}
                onStart={(id) => handleAction(id, 'start', () => startDevcontainer(id))}
                onStop={(id) => handleAction(id, 'stop', () => stopDevcontainer(id))}
                onDelete={(id) => handleAction(id, 'delete', () => deleteDevcontainer(id))}
                onEdit={(dc) => setModal({ mode: 'edit', dc })}
              />
            )
          }
        </QueryBoundary>
      </div>
      {modal &&
        (modal.mode === 'create' ? (
          <DevcontainerFormModal
            mode="create"
            onClose={() => setModal(null)}
            onSuccess={() => { setModal(null); refetch() }}
          />
        ) : (
          <DevcontainerFormModal
            mode="edit"
            devcontainer={modal.dc}
            onClose={() => setModal(null)}
            onSuccess={() => { setModal(null); refetch() }}
          />
        ))}
    </>
  )
}
