import { useState } from 'react'
import type { HarnessStatus } from '../lib/api/types'
import { authenticateHarness, installHarness } from '../lib/api'
import { cn } from '../lib/cn'

const checkIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const installIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
)

const loginIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
    <polyline points="10 17 15 12 10 7" />
    <line x1="15" y1="12" x2="3" y2="12" />
  </svg>
)

function SpinnerEl({ testId }: { testId: string }) {
  return (
    <span
      data-testid={testId}
      className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-border border-t-accent"
    />
  )
}

function Tick({ label }: { label: string }) {
  return (
    <span title={label} className="inline-flex h-6 w-6 items-center justify-center text-accent">
      {checkIcon}
    </span>
  )
}

function ActionIcon({ title, disabled, busy, busyTestId, onClick, children }: {
  title: string
  disabled?: boolean
  busy?: boolean
  busyTestId?: string
  onClick?: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled || busy}
      onClick={onClick}
      className={cn(
        'inline-flex h-6 w-6 items-center justify-center rounded-md border',
        disabled
          ? 'cursor-not-allowed border-border text-text-subtle opacity-50'
          : 'cursor-pointer border-border text-text hover:bg-surface-muted',
      )}
    >
      {busy ? <SpinnerEl testId={busyTestId ?? 'spinner'} /> : children}
    </button>
  )
}

export function HarnessList({ devcontainerId, harnesses, known, onChange }: {
  devcontainerId: string
  harnesses: HarnessStatus[]
  known: boolean
  onChange: () => void
}) {
  const [pending, setPending] = useState<Set<string>>(new Set())

  const run = (key: string, fn: () => Promise<unknown>) => {
    setPending((p) => new Set(p).add(key))
    void fn()
      .then(() => onChange())
      .catch(() => setPending((p) => { const n = new Set(p); n.delete(key); return n }))
  }

  return (
    <div className="rounded-xl border border-border bg-surface-rail">
      <div className="grid grid-cols-[1fr_120px_120px] border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.05em] text-text-subtle">
        <span>Harness</span>
        <span className="text-center">Installed</span>
        <span className="text-center">Authenticated</span>
      </div>
      {!known ? (
        <p className="px-3 py-4 text-[13px] text-text-muted">
          Runtime not connected — harness status unavailable.
        </p>
      ) : harnesses.length === 0 ? (
        <p className="px-3 py-4 text-[13px] text-text-muted">No harnesses reported.</p>
      ) : (
        harnesses.map((h) => (
          <div key={h.name} className="grid grid-cols-[1fr_120px_120px] items-center border-b border-border px-3 py-3 last:border-b-0">
            <span className="text-[13px] font-medium text-text">{h.name}</span>
            <span className="flex justify-center">
              {h.installed ? (
                <Tick label="Installed" />
              ) : (
                <ActionIcon
                  title={`Install ${h.name}`}
                  busy={pending.has('install:' + h.name)}
                  busyTestId={`spinner-install-${h.name}`}
                  onClick={() => run(`install:${h.name}`, () => installHarness(devcontainerId, h.name))}
                >
                  {installIcon}
                </ActionIcon>
              )}
            </span>
            <span className="flex justify-center">
              {h.authenticated ? (
                <Tick label="Authenticated" />
              ) : (
                <ActionIcon
                  title={h.installed ? `Authenticate ${h.name}` : `Install ${h.name} first`}
                  disabled={!h.installed}
                  busy={pending.has('auth:' + h.name)}
                  busyTestId={`spinner-auth-${h.name}`}
                  onClick={() => run(`auth:${h.name}`, () => authenticateHarness(devcontainerId, h.name))}
                >
                  {loginIcon}
                </ActionIcon>
              )}
            </span>
          </div>
        ))
      )}
    </div>
  )
}
