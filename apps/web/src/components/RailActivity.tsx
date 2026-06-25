import { useEffect } from 'react'
import { useMatch } from 'react-router'
import { fetchDelegatedRuns, useApiQuery } from '../lib/api'
import { useSseInvalidation } from '../lib/events'

function Empty({ children }: { children: string }) {
  return <p className="text-[12px] text-text-subtle">{children}</p>
}

function ActiveRuns({ id }: { id: string }) {
  const { register } = useSseInvalidation()
  const { state, refetch } = useApiQuery(() => fetchDelegatedRuns(id), [id])

  useEffect(() => register('delegated_runs', refetch), [register, refetch])

  if (state.kind === 'loading') return <Empty>Loading…</Empty>
  if (state.kind === 'error') return <Empty>Couldn't load runs.</Empty>

  const active = state.data.items.filter((r) => r.status === 'running')
  if (active.length === 0) return <Empty>No active runs.</Empty>

  return (
    <ul className="space-y-1.5">
      {active.map((run) => (
        <li
          key={run.run_id}
          className="rounded-md border border-border bg-surface-muted/40 px-2.5 py-1.5"
        >
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" />
            <span className="text-[12px] font-medium leading-tight text-text">{run.title}</span>
          </div>
          <div className="pl-3 font-mono text-[11px] leading-tight text-text-subtle">{run.run_id} · {run.harness} · {run.model}</div>
        </li>
      ))}
    </ul>
  )
}

// Scoped to the current devcontainer detail page — nothing renders elsewhere.
export function RailActivity() {
  const match = useMatch('/devcontainers/:id')
  if (!match?.params.id) return null

  return (
    <section>
      <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        Active runs
      </h3>
      <ActiveRuns id={match.params.id} />
    </section>
  )
}
