export type Scope = 'devcontainers' | 'agent_sessions' | 'runtime'

export interface InvalidationEvent {
  event_type: string
  scope: Scope
  ids: string[]
}

export type Health = 'connected' | 'reconnecting' | 'disconnected'

export type InvalidationCallback = (event: InvalidationEvent) => void
