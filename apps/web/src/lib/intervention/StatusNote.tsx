import type { ActionState } from './useInterventionAction'

/** Renders the awaiting/stale/error line beneath intervention controls. Copy is caller-supplied. */
export function StatusNote({
  state,
  awaitingNote,
  staleNote,
}: {
  state: ActionState
  awaitingNote: string
  staleNote: string
}) {
  if (state.kind === 'awaiting') return awaitingNote ? <div className="mt-1 text-[11px] text-accent">{awaitingNote}</div> : null
  if (state.kind === 'stale') return <div className="mt-1 text-[11px] text-bad">{staleNote}</div>
  if (state.kind === 'error') return <div className="mt-1 text-[11px] text-bad">{state.message}</div>
  return null
}
