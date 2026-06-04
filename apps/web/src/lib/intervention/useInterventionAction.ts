import { useState } from 'react'
import { ApiError } from '../api'

export type ActionState =
  | { kind: 'idle' }
  | { kind: 'submitting'; tag: string }
  | { kind: 'awaiting' }
  | { kind: 'stale' }
  | { kind: 'error'; message: string }

/** Owns the idle→submitting→awaiting/stale/error machine shared by approval and answer controls. */
export function useInterventionAction(staleCode: string) {
  const [state, setState] = useState<ActionState>({ kind: 'idle' })

  async function run(tag: string, submit: () => Promise<unknown>) {
    setState({ kind: 'submitting', tag })
    try {
      await submit()
      setState({ kind: 'awaiting' })
    } catch (err) {
      setState(
        err instanceof ApiError && err.code === staleCode
          ? { kind: 'stale' }
          : { kind: 'error', message: "Couldn't submit — try again." },
      )
    }
  }

  return { state, run }
}
