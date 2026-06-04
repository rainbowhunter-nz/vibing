import { useEffect } from 'react'
import { fetchConfig, fetchHealth, fetchRuntimeStatus, useApiQuery, type ConfigResponse } from '../lib/api'
import { useSseInvalidation } from '../lib/events'
import { cn } from '../lib/cn'

type ApiState =
  | { kind: 'loading' }
  | { kind: 'ok'; config: ConfigResponse }
  | { kind: 'error' }

function useApiState(): ApiState {
  const { state } = useApiQuery(
    () => Promise.all([fetchHealth(), fetchConfig()]).then(([, config]) => config),
    [],
  )
  if (state.kind === 'loading') return { kind: 'loading' }
  if (state.kind === 'error') return { kind: 'error' }
  return { kind: 'ok', config: state.data }
}

export function RailBackend() {
  const apiState = useApiState()
  const { state: runtimeState, refetch } = useApiQuery(fetchRuntimeStatus, [])
  const { register } = useSseInvalidation()

  useEffect(() => register('runtime', refetch), [register, refetch])

  const dotClass =
    apiState.kind === 'ok'
      ? 'bg-ok'
      : apiState.kind === 'error'
        ? 'bg-bad'
        : 'bg-text-subtle'
  const statusText =
    apiState.kind === 'ok'
      ? 'Connected'
      : apiState.kind === 'error'
        ? 'Unreachable'
        : 'Checking…'

  const workerConnected = runtimeState.kind === 'ready' ? runtimeState.data.worker_connected : false
  const workerDotClass = workerConnected ? 'bg-ok' : 'bg-text-subtle'
  const workerText = workerConnected ? 'Worker connected' : 'Worker disconnected'

  return (
    <section>
      <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        Backend
      </h3>
      <div className="mb-1.5 flex items-center gap-2 text-[12px] text-text-muted">
        <span className={cn('h-2 w-2 rounded-full', dotClass)} />
        {statusText}
      </div>
      {apiState.kind === 'ok' && (
        <>
          <div className="ml-4 text-[11px] text-text-subtle">service: {apiState.config.app_name}</div>
          <div className="ml-4 text-[11px] text-text-subtle">api: {apiState.config.api_v1_prefix}</div>
        </>
      )}
      {apiState.kind === 'error' && (
        <div className="ml-4 text-[11px] text-text-subtle">service: unavailable</div>
      )}
      <div className="mt-2 flex items-center gap-2 text-[12px] text-text-muted">
        <span className={cn('h-2 w-2 rounded-full', workerDotClass)} />
        {workerText}
      </div>
    </section>
  )
}
