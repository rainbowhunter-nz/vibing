import { useState } from 'react'
import type { DelegatedRun } from '../lib/api/types'
import { stopDelegatedRun } from '../lib/api'
import { formatRelativeTime } from '../lib/time'
import { cn } from '../lib/cn'
import { Modal } from './Modal'

function badgeClass(status: DelegatedRun['status']): string {
  switch (status) {
    case 'running':
      return 'bg-accent/15 text-accent'
    case 'failed':
      return 'bg-bad/15 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function errorText(error: DelegatedRun['error']): string | null {
  if (!error) return null
  const code = error.exit_code
  const tail = error.stderr_tail
  return [typeof code === 'number' ? `exit ${code}` : null, typeof tail === 'string' ? tail : null].filter(Boolean).join(' · ') || JSON.stringify(error)
}

function RunRow({ devcontainerId, run, onChange, onOpen }: {
  devcontainerId: string
  run: DelegatedRun
  onChange: () => void
  onOpen: () => void
}) {
  const [busy, setBusy] = useState(false)

  async function stop(e: React.MouseEvent) {
    e.stopPropagation()
    setBusy(true)
    try {
      await stopDelegatedRun(devcontainerId, run.run_id)
      onChange()
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full px-3 py-2.5 text-left hover:bg-surface-rail"
    >
      <div className="flex items-center gap-2">
        {run.status === 'running' && <span className="h-2 w-2 shrink-0 rounded-full bg-accent" />}
        <span className="font-mono text-[12px] font-semibold text-text">{run.run_id}</span>
        <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', badgeClass(run.status))}>
          {run.status}
        </span>
        {run.status === 'running' && (
          <span
            role="button"
            tabIndex={0}
            title={`Stop ${run.run_id}`}
            aria-disabled={busy}
            onClick={stop}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') stop(e as unknown as React.MouseEvent)
            }}
            className="ml-auto rounded-md border border-border px-2 py-0.5 text-[11px] text-text hover:bg-surface-muted aria-disabled:opacity-40"
          >
            Stop
          </span>
        )}
      </div>
      <div className="mt-1 text-[11px] text-text-subtle">
        {run.harness} · {run.model} · {formatRelativeTime(run.started_at)}
      </div>
    </button>
  )
}

function RunDialog({ run, onClose }: { run: DelegatedRun; onClose: () => void }) {
  const error = errorText(run.error)
  const body = run.status === 'failed' ? error : run.result

  return (
    <Modal
      ariaLabel={`Run ${run.run_id}`}
      onClose={onClose}
      header={
        <>
          <span className="font-mono text-[13px] font-semibold text-text">{run.run_id}</span>
          <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', badgeClass(run.status))}>
            {run.status}
          </span>
        </>
      }
    >
      <div className="mb-3 text-[11px] text-text-subtle">
        {run.harness} · {run.model} · {formatRelativeTime(run.started_at)}
      </div>
      {body ? (
        <pre className={cn('overflow-x-auto rounded-md border border-border bg-surface-muted p-3 text-[12px]', run.status === 'failed' ? 'text-bad' : 'text-text-muted')}>
          {body}
        </pre>
      ) : (
        <p className="text-[12px] text-text-muted">
          {run.status === 'running' ? 'Run in progress — no result yet.' : 'No output recorded.'}
        </p>
      )}
    </Modal>
  )
}

export function DelegatedRuns({ devcontainerId, runs, onChange, emptyMessage, className = 'max-h-[26rem]' }: {
  devcontainerId: string
  runs: DelegatedRun[]
  onChange: () => void
  emptyMessage?: string
  className?: string
}) {
  const [openId, setOpenId] = useState<string | null>(null)

  if (runs.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-[13px] text-text-muted">
        {emptyMessage ?? 'No delegated runs — the harness will list them here when it spawns one.'}
      </p>
    )
  }

  const openRun = runs.find((r) => r.run_id === openId) ?? null

  return (
    <>
      <div className={cn('overflow-y-auto rounded-xl border border-border bg-surface-muted', className)}>
        <div className="divide-y divide-border">
          {runs.map((run) => (
            <RunRow
              key={run.run_id}
              devcontainerId={devcontainerId}
              run={run}
              onChange={onChange}
              onOpen={() => setOpenId(run.run_id)}
            />
          ))}
        </div>
      </div>
      {openRun && <RunDialog run={openRun} onClose={() => setOpenId(null)} />}
    </>
  )
}
