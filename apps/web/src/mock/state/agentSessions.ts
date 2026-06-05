import type { AgentSession, AgentSessionList, AgentSessionStartBody } from '../../lib/api/types'
import { seedAgentSessions } from './seeds'

const SEED: AgentSession[] = seedAgentSessions.map((s) => ({ ...s }))

let store: AgentSession[] = SEED.map((s) => ({ ...s }))
let nextIdSeq = 100

function now(): string {
  return new Date().toISOString()
}

export class NotFoundError extends Error {
  readonly code = 'AGENT_SESSION_NOT_FOUND'
  constructor(id: string) {
    super(`Agent session not found: ${id}`)
  }
}

function findIdx(id: string): number {
  const idx = store.findIndex((s) => s.id === id)
  if (idx === -1) throw new NotFoundError(id)
  return idx
}

export function resetAgentSessions(): void {
  store = SEED.map((s) => ({ ...s }))
  nextIdSeq = 100
}

export function listAgentSessions(devcontainerId: string): AgentSessionList {
  return {
    items: store
      .filter((s) => s.devcontainer_id === devcontainerId)
      .map((s) => ({ ...s })),
  }
}

export function startAgentSession(devcontainerId: string, body: AgentSessionStartBody): AgentSession {
  void body
  const ts = now()
  const session: AgentSession = {
    id: `as-mock-${String(nextIdSeq++).padStart(4, '0')}`,
    devcontainer_id: devcontainerId,
    status: 'starting',
    started_at: null,
    ended_at: null,
    last_event_at: null,
    created_at: ts,
    updated_at: ts,
  }
  store.push(session)
  return { ...session }
}

export function stopAgentSession(devcontainerId: string, sessionId: string): AgentSession {
  const idx = findIdx(sessionId)
  if (store[idx].devcontainer_id !== devcontainerId) throw new NotFoundError(sessionId)
  const ts = now()
  store[idx] = { ...store[idx], status: 'stopped', ended_at: ts, updated_at: ts }
  return { ...store[idx] }
}
