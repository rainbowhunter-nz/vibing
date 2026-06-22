import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { HarnessList } from '../components/HarnessList'
import { Dialog } from '../components/Dialog'
import { PlayIcon, StopIcon, TrashIcon, SpinnerIcon, InjectIcon } from '../components/icons'
import {
  fetchDevcontainer,
  startDevcontainer,
  stopDevcontainer,
  removeContainer,
  injectRuntime,
  fetchHarnesses,
  useApiQuery,
  ApiError,
} from '../lib/api'
import type { DevcontainerView } from '../lib/api/types'
import { formatRelativeTime } from '../lib/time'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running':
    case 'starting':
    case 'stopping':
      return 'bg-accent/15 text-accent'
    case 'error':
      return 'bg-bad/15 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', statusBadgeClass(status))}>
      {status}
    </span>
  )
}

function SourceBadge({ source }: { source: string }) {
  return (
    <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-text-muted">
      {source}
    </span>
  )
}

function IconButton({
  title,
  busy,
  disabled,
  danger,
  onClick,
  children,
}: {
  title: string
  busy: boolean
  disabled?: boolean
  danger?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  const inactive = busy || disabled
  return (
    <button
      type="button"
      title={title}
      disabled={inactive}
      onClick={onClick}
      className={cn(
        'flex h-7 w-7 items-center justify-center rounded-[5px]',
        inactive
          ? 'cursor-not-allowed opacity-40'
          : danger
            ? 'cursor-pointer text-bad hover:bg-surface-muted'
            : 'cursor-pointer text-text-muted hover:bg-surface-muted',
      )}
    >
      {busy ? <SpinnerIcon /> : children}
    </button>
  )
}

type ActionKind = 'start' | 'stop' | 'inject' | 'remove'

export function LifecycleHeader({
  dc,
  busy,
  onAction,
}: {
  dc: DevcontainerView
  busy: boolean
  onAction: (kind: ActionKind) => void
}) {
  const [showDetails, setShowDetails] = useState(false)
  const running = dc.status === 'running'
  const transitioning = dc.status === 'starting' || dc.status === 'stopping'

  return (
    <div className="border-b border-border bg-surface-rail px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <button
          type="button"
          onClick={() => setShowDetails(true)}
          className="text-[15px] font-semibold text-text hover:text-accent"
          title="View details"
        >
          {dc.name}
        </button>
        <StatusBadge status={dc.status} />
        <SourceBadge source={dc.source} />
        <div className="ml-auto flex items-center gap-1">
          {running ? (
            <IconButton title="Stop" busy={busy} onClick={() => onAction('stop')}>
              <StopIcon />
            </IconButton>
          ) : (
            <IconButton title="Start" busy={busy || transitioning} onClick={() => onAction('start')}>
              <PlayIcon />
            </IconButton>
          )}
          <IconButton
            title="Remove container"
            danger
            busy={busy}
            onClick={() => { if (!busy && confirm(`Remove the container for ${dc.name}? The devcontainer stays in the list.`)) onAction('remove') }}
          >
            <TrashIcon />
          </IconButton>
        </div>
      </div>
      {showDetails && <DetailsDialog dc={dc} onClose={() => setShowDetails(false)} />}
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-text-subtle">{label}</div>
      <div className="mt-0.5 text-[13px] text-text">{value}</div>
    </div>
  )
}

function DetailsDialog({ dc, onClose }: { dc: DevcontainerView; onClose: () => void }) {
  return (
    <Dialog title={dc.name} onClose={onClose}>
      <div className="space-y-3">
        <DetailRow label="Status" value={dc.status} />
        <DetailRow label="Local path" value={dc.local_path} />
        <DetailRow label="Created" value={dc.created_at ? formatRelativeTime(dc.created_at) : '—'} />
        <DetailRow label="Updated" value={dc.updated_at ? formatRelativeTime(dc.updated_at) : '—'} />
      </div>
    </Dialog>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{children}</h3>
}

function ControlPanel({ dc }: { dc: DevcontainerView }) {
  const { register } = useSseInvalidation()
  const { state: harnessState, refetch: refetchHarnesses } = useApiQuery(() => fetchHarnesses(dc.id), [dc.id])

  useEffect(() => register('harnesses', refetchHarnesses), [register, refetchHarnesses])

  return (
    <div className="p-4">
      <section>
        <SectionTitle>Coding harnesses</SectionTitle>
        {harnessState.kind === 'ready' ? (
          <HarnessList devcontainerId={dc.id} harnesses={harnessState.data.items} known={harnessState.data.known} onChange={refetchHarnesses} />
        ) : harnessState.kind === 'error' ? (
          <ErrorState {...loadError('harnesses')} />
        ) : (
          <p className="text-[13px] text-text-muted">Loading harnesses…</p>
        )}
      </section>
    </div>
  )
}

function errorElement(error: unknown) {
  if (error instanceof ApiError && error.code === 'DEVCONTAINER_NOT_FOUND') {
    return <ErrorState title="Devcontainer not found" helper="This devcontainer doesn't exist or has been deleted." />
  }
  return <ErrorState {...loadError('devcontainer')} />
}

export function DevcontainerDetail() {
  const { id } = useParams<{ id: string }>()
  const { register } = useSseInvalidation()
  const { state, refetch } = useApiQuery(() => fetchDevcontainer(id!), [id])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => register('devcontainers', refetch), [register, refetch])
  useEffect(() => register('runtime', refetch), [register, refetch])

  async function act(kind: ActionKind, dc: DevcontainerView) {
    setBusy(true)
    setError(null)
    try {
      if (kind === 'start') await startDevcontainer(dc.id)
      else if (kind === 'stop') await stopDevcontainer(dc.id)
      else if (kind === 'inject') await injectRuntime(dc.id)
      else if (kind === 'remove') await removeContainer(dc.id)
      refetch()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0">
        <PageHeader title="Devcontainer" crumbs="Detail" />
      </div>
      <QueryBoundary state={state} error={errorElement(state.kind === 'error' ? state.error : null)}>
        {(dc) => (
          <div className="min-h-0 flex-1 overflow-auto">
            {error && (
              <div className="px-4 pt-3">
                <ErrorState title="Action failed" helper={error} />
              </div>
            )}
            <LifecycleHeader dc={dc} busy={busy} onAction={(kind) => act(kind, dc)} />
            <ControlPanel dc={dc} />
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
