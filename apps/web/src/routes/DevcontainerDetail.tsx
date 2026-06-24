import { useEffect, useRef, useState } from 'react'
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
  stopRuntime,
  streamRuntimeLogs,
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

type ActionKind = 'start' | 'stop' | 'inject' | 'remove' | 'stop-runtime'

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

const RUNTIME_LABEL: Record<string, string> = {
  connected: 'Connected',
  launching: 'Launching…',
  disconnected: 'Disconnected',
  error: 'Error',
}

export function RuntimeSection({
  dc,
  busy,
  onAction,
}: {
  dc: DevcontainerView
  busy: boolean
  onAction: (kind: ActionKind) => void
}) {
  const running = dc.status === 'running'
  const state = dc.runtime.state
  const connected = state === 'connected'
  const launching = state === 'launching'
  const error = state === 'error'
  const [logs, setLogs] = useState('')
  const [showLogs, setShowLogs] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const preRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (!showLogs) return
    const controller = new AbortController()
    const run = async () => {
      setLogs('')
      setStreaming(true)
      try {
        await streamRuntimeLogs(dc.id, controller.signal, (text) => setLogs((prev) => prev + text))
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setLogs((prev) => prev + `\n[stream error: ${e instanceof Error ? e.message : String(e)}]`)
      } finally {
        setStreaming(false)
      }
    }
    void run()
    return () => controller.abort()
  }, [showLogs, dc.id])

  useEffect(() => {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight
  }, [logs])

  return (
    <section className="mb-5">
      <SectionTitle>Runtime</SectionTitle>
      <div className="flex items-center gap-2 text-[13px]">
        <span
          className={cn(
            'h-2 w-2 rounded-full',
            connected ? 'bg-ok' : launching ? 'bg-accent' : error ? 'bg-bad' : 'bg-text-subtle',
          )}
        />
        <span className={connected ? 'text-text' : 'text-text-muted'}>{RUNTIME_LABEL[state]}</span>
        <div className="ml-auto flex items-center gap-1">
          <IconButton title="View runtime logs" busy={false} onClick={() => setShowLogs(true)}>
            <span className="text-[11px] font-medium">Logs</span>
          </IconButton>
          {connected ? (
            <IconButton title="Stop runtime" busy={busy} onClick={() => onAction('stop-runtime')}>
              <StopIcon />
            </IconButton>
          ) : (
            <IconButton
              title={running ? 'Inject runtime' : 'Start the container to inject runtime'}
              busy={busy && running}
              disabled={!running}
              onClick={() => onAction('inject')}
            >
              <InjectIcon />
            </IconButton>
          )}
        </div>
      </div>
      {showLogs && (
        <Dialog title="Runtime logs" onClose={() => setShowLogs(false)}>
          <div className="mb-1 flex items-center gap-1.5 text-[11px] text-text-muted">
            <span className={cn('h-1.5 w-1.5 rounded-full', streaming ? 'bg-ok' : 'bg-text-subtle')} />
            {streaming ? 'live' : 'ended'}
          </div>
          <pre
            ref={preRef}
            className="max-h-80 overflow-auto whitespace-pre-wrap text-[12px] text-text-muted"
          >
            {logs || 'Waiting for output…'}
          </pre>
        </Dialog>
      )}
    </section>
  )
}

function ControlPanel({
  dc,
  busy,
  onAction,
}: {
  dc: DevcontainerView
  busy: boolean
  onAction: (kind: ActionKind) => void
}) {
  const { register } = useSseInvalidation()
  const { state: harnessState, refetch: refetchHarnesses } = useApiQuery(() => fetchHarnesses(dc.id), [dc.id])

  // Harness status depends on the runtime: a runtime connect/disconnect changes
  // whether it is known, so refetch on both scopes.
  useEffect(() => register('harnesses', refetchHarnesses), [register, refetchHarnesses])
  useEffect(() => register('runtime', refetchHarnesses), [register, refetchHarnesses])

  return (
    <div className="p-4">
      <RuntimeSection dc={dc} busy={busy} onAction={onAction} />
      <section>
        <SectionTitle>Coding harnesses</SectionTitle>
        {harnessState.kind === 'ready' ? (
          <HarnessList devcontainerId={dc.id} harnesses={harnessState.data.items} known={harnessState.data.known} running={dc.status === 'running'} onChange={refetchHarnesses} />
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
      else if (kind === 'stop-runtime') await stopRuntime(dc.id)
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
            <ControlPanel dc={dc} busy={busy} onAction={(kind) => act(kind, dc)} />
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
