import { PageHeader } from '../components/PageHeader'
import { cn } from '../lib/cn'
import { useScenario } from '../mock/useScenario'
import { useStreamState } from '../mock/useMockSse'
import { SCENARIOS, type Scenario } from '../mock/scenario'
import { emitInvalidation, setStreamState } from '../mock/events'
import type { Scope } from '../lib/events/types'
import type { StreamState } from '../mock/events'

const DESCRIPTIONS: Record<Scenario, string> = {
  happy: 'Healthy baseline — all endpoints return fixture data.',
  empty: 'Empty collections — list endpoints return zero items.',
  'api-error': '500 error envelope on all endpoints.',
  'network-down': 'Network-level failure — simulates no connectivity.',
  'stale-action': '409 conflict on all endpoints.',
  'not-found': '404 not-found envelope on all endpoints.',
}

const SCOPES: Scope[] = ['devcontainers', 'agent_sessions', 'inbox', 'approvals', 'runtime']
const SCOPE_DESC: Record<Scope, string> = {
  devcontainers: 'Triggers devcontainer list/detail refetch.',
  agent_sessions: 'Triggers agent session list refetch.',
  inbox: 'Triggers inbox list refetch.',
  approvals: 'Triggers approvals list refetch.',
  runtime: 'Triggers runtime status refetch.',
}

const STREAM_STATES: StreamState[] = ['connected', 'reconnecting', 'disconnected']
const STREAM_DESC: Record<StreamState, string> = {
  connected: 'EventSource open — health shows connected.',
  reconnecting: 'Transient error — browser auto-reconnects.',
  disconnected: 'Fatal close — connection lost.',
}

export function MockScenarios() {
  const [active, setScenario] = useScenario()
  const streamState = useStreamState()

  return (
    <>
      <PageHeader title="Mock Scenarios" />
      <div className="flex-1 overflow-auto">
        <div className="px-6 py-5">
          <p className="mb-4 text-[13px] text-text-muted">
            Dev-only — switches the active global scenario for all mock API responses.
          </p>
          <div className="flex flex-col gap-2">
            {SCENARIOS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setScenario(s)}
                aria-pressed={s === active}
                className={cn(
                  'flex max-w-[520px] flex-col rounded-md border px-4 py-3 text-left transition-colors',
                  s === active
                    ? 'border-accent bg-accent-bg'
                    : 'border-border bg-surface-muted hover:bg-surface-muted/80',
                )}
              >
                <span className={cn('text-[13px] font-medium', s === active ? 'text-text' : 'text-text-muted')}>
                  {s}
                  {s === active && <span className="ml-2 text-[11px] font-normal text-accent">active</span>}
                </span>
                <span className="mt-0.5 text-[12px] text-text-subtle">{DESCRIPTIONS[s]}</span>
              </button>
            ))}
          </div>

          <h2 className="mb-3 mt-8 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            Event Stream
          </h2>
          <p className="mb-3 text-[13px] text-text-muted">
            Force stream connection state or manually emit an invalidation to trigger a refetch.
          </p>

          <div className="mb-5">
            <p className="mb-2 text-[12px] font-medium text-text-muted">Connection state</p>
            <div className="flex flex-col gap-2">
              {STREAM_STATES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStreamState(s)}
                  aria-pressed={s === streamState}
                  className={cn(
                    'flex max-w-[520px] flex-col rounded-md border px-4 py-3 text-left transition-colors',
                    s === streamState
                      ? 'border-accent bg-accent-bg'
                      : 'border-border bg-surface-muted hover:bg-surface-muted/80',
                  )}
                >
                  <span className={cn('text-[13px] font-medium', s === streamState ? 'text-text' : 'text-text-muted')}>
                    {s}
                    {s === streamState && <span className="ml-2 text-[11px] font-normal text-accent">active</span>}
                  </span>
                  <span className="mt-0.5 text-[12px] text-text-subtle">{STREAM_DESC[s]}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[12px] font-medium text-text-muted">Emit invalidation</p>
            <div className="flex flex-col gap-2">
              {SCOPES.map((scope) => (
                <button
                  key={scope}
                  type="button"
                  onClick={() => emitInvalidation(scope)}
                  className="flex max-w-[520px] flex-col rounded-md border border-border bg-surface-muted px-4 py-3 text-left hover:bg-surface-muted/80"
                >
                  <span className="text-[13px] font-medium text-text-muted">{scope}</span>
                  <span className="mt-0.5 text-[12px] text-text-subtle">{SCOPE_DESC[scope]}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
