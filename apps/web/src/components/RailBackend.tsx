import { useEffect, useState } from 'react'
import { fetchConfig, fetchHealth, type ConfigResponse } from '../lib/api'
import { cn } from '../lib/cn'

type State =
  | { kind: 'loading' }
  | { kind: 'ok'; config: ConfigResponse }
  | { kind: 'error' }

export function RailBackend() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchHealth(), fetchConfig()])
      .then(([, config]) => {
        if (!cancelled) setState({ kind: 'ok', config })
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  const dotClass =
    state.kind === 'ok'
      ? 'bg-ok'
      : state.kind === 'error'
        ? 'bg-bad'
        : 'bg-text-subtle'
  const statusText =
    state.kind === 'ok'
      ? 'Connected'
      : state.kind === 'error'
        ? 'Unreachable'
        : 'Checking…'

  return (
    <section>
      <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        Backend
      </h3>
      <div className="mb-1.5 flex items-center gap-2 text-[12px] text-text-muted">
        <span className={cn('h-2 w-2 rounded-full', dotClass)} />
        {statusText}
      </div>
      {state.kind === 'ok' && (
        <>
          <div className="ml-4 text-[11px] text-text-subtle">service: {state.config.app_name}</div>
          <div className="ml-4 text-[11px] text-text-subtle">api: {state.config.api_v1_prefix}</div>
        </>
      )}
      {state.kind === 'error' && (
        <div className="ml-4 text-[11px] text-text-subtle">service: unavailable</div>
      )}
    </section>
  )
}
