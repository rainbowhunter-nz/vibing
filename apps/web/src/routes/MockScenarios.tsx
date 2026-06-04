import { PageHeader } from '../components/PageHeader'
import { cn } from '../lib/cn'
import { useScenario } from '../mock/useScenario'
import { SCENARIOS, type Scenario } from '../mock/scenario'

const DESCRIPTIONS: Record<Scenario, string> = {
  happy: 'Healthy baseline — all endpoints return fixture data.',
  empty: 'Empty collections — list endpoints return zero items.',
  'api-error': '500 error envelope on all endpoints.',
  'network-down': 'Network-level failure — simulates no connectivity.',
  'stale-action': '409 conflict on all endpoints.',
  'not-found': '404 not-found envelope on all endpoints.',
}

export function MockScenarios() {
  const [active, setScenario] = useScenario()

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
        </div>
      </div>
    </>
  )
}
