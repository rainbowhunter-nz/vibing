import { NavLink } from 'react-router'
import { cn } from '../lib/cn'
import { useScenario } from './useScenario'
import { useStreamState } from './useMockSse'
import { emitInvalidation, setStreamState } from './events'
import { playSessionStream } from './agentSessionStreams'
import type { Scope } from '../lib/events/types'
import type { StreamState } from './events'

// A seeded active session (running, on a running devcontainer) for live-chat inspection.
const LIVE_DEMO_SESSION = 'as-seed-0005'

const SCOPES: Scope[] = ['devcontainers', 'agent_sessions', 'inbox', 'approvals', 'runtime']
const STREAM_STATES: StreamState[] = ['connected', 'reconnecting', 'disconnected']

const STATE_DOT: Record<StreamState, string> = {
  connected: 'bg-ok',
  reconnecting: 'bg-accent',
  disconnected: 'bg-bad',
}

export function RailMock() {
  const [active] = useScenario()
  const streamState = useStreamState()

  return (
    <section>
      <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        Mock
      </h3>
      <div className="mb-1.5 flex items-center gap-2 text-[12px] text-text-muted">
        <span className="h-2 w-2 rounded-full bg-accent" />
        {active}
      </div>
      <NavLink
        to="/mock"
        className={({ isActive }) =>
          cn(
            'ml-4 text-[11px] text-text-subtle underline-offset-2 hover:underline',
            isActive && 'font-medium text-text',
          )
        }
      >
        switch scenario
      </NavLink>

      <div className="mt-3">
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
          Stream
        </p>
        <div className="mb-2 flex items-center gap-1.5 text-[11px] text-text-muted">
          <span className={cn('h-1.5 w-1.5 rounded-full', STATE_DOT[streamState])} />
          {streamState}
        </div>
        <div className="mb-2 flex flex-wrap gap-1">
          {STREAM_STATES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStreamState(s)}
              className={cn(
                'rounded px-1.5 py-0.5 text-[10px]',
                s === streamState
                  ? 'bg-accent text-white'
                  : 'bg-surface-muted text-text-muted hover:bg-border',
              )}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-1">
          {SCOPES.map((scope) => (
            <button
              key={scope}
              type="button"
              onClick={() => emitInvalidation(scope)}
              className="rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-text-subtle hover:bg-border"
            >
              {scope}
            </button>
          ))}
        </div>
        <p className="mt-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
          Session stream
        </p>
        <button
          type="button"
          onClick={() => playSessionStream(LIVE_DEMO_SESSION, { tokenDelayMs: 150 })}
          className="rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-text-subtle hover:bg-border"
        >
          play live deltas ({LIVE_DEMO_SESSION.slice(0, 11)})
        </button>
      </div>
    </section>
  )
}
