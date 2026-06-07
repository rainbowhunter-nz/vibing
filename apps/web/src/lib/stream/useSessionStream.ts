// Per-session live-stream hook (ADR-0010, VIB-109). Opens a SEPARATE EventSource to the
// per-session turn-delta endpoint — NOT routed through the global invalidation coordinator
// — only while `active`. Feeds the pure liveReducer; on the terminal run_ended delta it
// fires onRunEnded so the caller refetches the canonical transcript and reconciles by id.
// Resting/historical sessions pass active=false: no stream is opened.

import { useEffect, useRef, useState } from 'react'
import { openAgentSessionStream } from '../api/endpoints'
import type { TurnDelta } from '../api/types'
import { emptyLiveState, liveReducer, type LiveState } from './mergeTurns'

export function useSessionStream(
  devcontainerId: string,
  sessionId: string,
  active: boolean,
  onRunEnded: () => void,
): LiveState {
  // The owning ConversationBody is keyed by sessionId, so this hook remounts (and live
  // state resets) on session switch — no manual cross-session reset needed here.
  const [live, setLive] = useState<LiveState>(emptyLiveState)

  // Keep the latest onRunEnded without re-opening the stream when it changes identity.
  const onRunEndedRef = useRef(onRunEnded)
  useEffect(() => {
    onRunEndedRef.current = onRunEnded
  }, [onRunEnded])

  useEffect(() => {
    if (!active || typeof EventSource === 'undefined') return
    const es = openAgentSessionStream(devcontainerId, sessionId)
    if (!es || typeof es.addEventListener !== 'function') return
    const handle = (e: Event) => {
      const msg = e as MessageEvent
      let delta: TurnDelta
      try {
        delta = JSON.parse(msg.data as string)
      } catch {
        return // malformed line — ignore
      }
      setLive((prev) => liveReducer(prev, delta))
      if (delta.kind === 'run_ended') onRunEndedRef.current()
    }
    es.addEventListener('turn_delta', handle)
    return () => {
      es.removeEventListener('turn_delta', handle)
      es.close()
    }
  }, [devcontainerId, sessionId, active])

  return live
}
