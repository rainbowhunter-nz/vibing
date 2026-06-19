export type Scope = 'devcontainers' | 'runtime' | 'harnesses' | 'delegated_runs'

export interface InvalidationEvent {
  event_type: string
  scope: Scope
  ids: string[]
}

export type Health = 'connected' | 'reconnecting' | 'disconnected'

export type InvalidationCallback = (event: InvalidationEvent) => void
