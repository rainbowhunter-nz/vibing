import { createContext } from 'react'
import type { Health, InvalidationCallback, Scope } from './types'

export interface SseContextValue {
  register(scope: Scope, cb: InvalidationCallback): () => void
  health: Health
}

export const SseContext = createContext<SseContextValue | null>(null)
