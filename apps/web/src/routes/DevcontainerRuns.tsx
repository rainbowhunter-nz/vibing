import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { DelegatedRuns } from '../components/DelegatedRuns'
import { fetchDevcontainer, fetchDelegatedRuns, useApiQuery } from '../lib/api'
import type { DelegatedRun, DelegatedRunStatus } from '../lib/api/types'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'

type Filter = 'all' | DelegatedRunStatus
const FILTERS: Filter[] = ['all', 'running', 'completed', 'failed', 'stopped']

function FilterTabs({ runs, active, onSelect }: {
  runs: DelegatedRun[]
  active: Filter
  onSelect: (f: Filter) => void
}) {
  const count = (f: Filter) => (f === 'all' ? runs.length : runs.filter((r) => r.status === f).length)
  return (
    <div className="mb-3 flex flex-wrap gap-1.5">
      {FILTERS.map((f) => (
        <button
          key={f}
          type="button"
          onClick={() => onSelect(f)}
          className={cn(
            'rounded-full px-2.5 py-1 text-[12px] font-medium capitalize',
            f === active ? 'bg-accent text-bg' : 'bg-surface-muted text-text-muted hover:text-text',
          )}
        >
          {f} <span className="opacity-60">{count(f)}</span>
        </button>
      ))}
    </div>
  )
}

function RunsPanel({ devcontainerId }: { devcontainerId: string }) {
  const { register } = useSseInvalidation()
  const { state, refetch } = useApiQuery(() => fetchDelegatedRuns(devcontainerId), [devcontainerId])
  const [filter, setFilter] = useState<Filter>('all')

  useEffect(() => register('delegated_runs', refetch), [register, refetch])

  if (state.kind === 'error') return <ErrorState {...loadError('delegated runs')} />
  if (state.kind !== 'ready') return <p className="text-[13px] text-text-muted">Loading runs…</p>

  const runs = state.data.items
  const shown = filter === 'all' ? runs : runs.filter((r) => r.status === filter)

  return (
    <>
      <FilterTabs runs={runs} active={filter} onSelect={setFilter} />
      <DelegatedRuns
        devcontainerId={devcontainerId}
        runs={shown}
        onChange={refetch}
        className="max-h-full"
        emptyMessage={filter === 'all' ? 'No delegated runs yet.' : `No ${filter} runs.`}
      />
    </>
  )
}

export function DevcontainerRuns() {
  const { id } = useParams<{ id: string }>()
  const { register } = useSseInvalidation()
  const { state, refetch } = useApiQuery(() => fetchDevcontainer(id!), [id])

  useEffect(() => register('devcontainers', refetch), [register, refetch])

  const crumbs =
    state.kind === 'ready' ? (
      <Link to={`/devcontainers/${id}`} className="text-accent hover:underline">
        ← {state.data.name}
      </Link>
    ) : undefined

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0">
        <PageHeader title="Delegated runs" crumbs={crumbs} />
      </div>
      <QueryBoundary state={state} error={<ErrorState {...loadError('devcontainer')} />}>
        {(dc) => (
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <RunsPanel devcontainerId={dc.id} />
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
