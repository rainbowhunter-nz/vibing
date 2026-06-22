import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { HarnessList } from '../components/HarnessList'
import { Dialog } from '../components/Dialog'
import {
  fetchDevcontainer,
  startDevcontainer,
  stopDevcontainer,
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

const RUNNING = new Set(['running', 'starting', 'stopping'])

function ConnDot({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-text-muted">
      <span className={cn('h-2 w-2 rounded-full', ok ? 'bg-ok' : 'bg-text-subtle')} />
      {label}
    </span>
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

function LifecycleHeader({ dc, onChange }: { dc: DevcontainerView; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const running = RUNNING.has(dc.status)

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    try {
      await fn()
      onChange()
    } finally {
      setBusy(false)
    }
  }

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
        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', statusBadgeClass(dc.status))}>
          {dc.status}
        </span>
        <ConnDot
          label={dc.runtime.runtime_connected ? 'runtime' : 'runtime not connected'}
          ok={dc.runtime.runtime_connected}
        />
        <div className="ml-auto flex items-center gap-2">
          {dc.status === 'running' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => act(() => stopDevcontainer(dc.id))}
              className="rounded-lg border border-border px-3 py-1.5 text-[13px] font-medium text-text hover:bg-surface-muted disabled:opacity-40"
            >
              Stop
            </button>
          ) : (
            <button
              type="button"
              disabled={busy || running}
              onClick={() => act(() => startDevcontainer(dc.id))}
              className="rounded-lg bg-accent px-3 py-1.5 text-[13px] font-medium text-bg hover:bg-accent/90 disabled:opacity-40"
            >
              Start
            </button>
          )}
        </div>
      </div>
      {showDetails && <DetailsDialog dc={dc} onClose={() => setShowDetails(false)} />}
    </div>
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
          <HarnessList devcontainerId={dc.id} harnesses={harnessState.data.items} onChange={refetchHarnesses} />
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

  useEffect(() => register('devcontainers', refetch), [register, refetch])
  useEffect(() => register('runtime', refetch), [register, refetch])

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0">
        <PageHeader title="Devcontainer" crumbs="Detail" />
      </div>
      <QueryBoundary state={state} error={errorElement(state.kind === 'error' ? state.error : null)}>
        {(dc) => (
          <div className="min-h-0 flex-1 overflow-auto">
            <LifecycleHeader dc={dc} onChange={refetch} />
            <ControlPanel dc={dc} />
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
