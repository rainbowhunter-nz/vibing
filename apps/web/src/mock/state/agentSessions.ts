import type { AgentSession, AgentSessionDetail, AgentSessionList, AgentSessionResumeBody, AgentSessionStartBody, AgentSessionTranscript, TranscriptTurn } from '../../lib/api/types'
import { getDevcontainer } from './devcontainers'
import { seedAgentSessions } from './seeds'

const SESSION_SUMMARIES: Record<string, string> = {
  'as-seed-0004': 'All tests passed. Ready to merge.',
  'as-seed-0006': 'Error: command not found: pytest',
}

// Seeded transcript turns per session id. as-seed-0004 (completed) has a full
// conversation with a tool_use block so the UI demonstrates both bubbles and a tool pill.
const SEED_TRANSCRIPTS: Record<string, TranscriptTurn[]> = {
  'as-seed-0004': [
    {
      id: 'as-seed-0004-u1',
      role: 'user',
      blocks: [{ kind: 'text', text: 'Fix the flaky test in auth' }],
      at: '2024-01-13T12:00:00.000Z',
    },
    {
      id: 'as-seed-0004-a1',
      role: 'assistant',
      blocks: [
        { kind: 'tool_use', name: 'Bash', summary: 'ran pytest --tb=short auth/' },
        { kind: 'text', text: 'All tests passed. Ready to merge.' },
      ],
      at: '2024-01-13T12:25:00.000Z',
    },
  ],
}

let transcriptStore: Record<string, TranscriptTurn[]> = { ...SEED_TRANSCRIPTS }

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

export class ActiveSessionError extends Error {
  readonly code = 'AGENT_SESSION_STILL_ACTIVE'
  constructor(id: string) {
    super(`Cannot delete active agent session: ${id}`)
  }
}

export class NonRestingError extends Error {
  readonly code = 'AGENT_SESSION_NOT_RESTING'
  constructor(id: string) {
    super(`Agent session is not in a resting state: ${id}`)
  }
}

export class OtherSessionActiveError extends Error {
  readonly code = 'AGENT_SESSION_ACTIVE'
  constructor(devcontainerId: string) {
    super(`An agent session is already active for devcontainer: ${devcontainerId}`)
  }
}

const ACTIVE_STATUSES = new Set(['starting', 'running', 'waiting_for_approval'])
const RESTING_STATUSES = new Set(['completed', 'failed', 'stopped'])

function findIdx(id: string): number {
  const idx = store.findIndex((s) => s.id === id)
  if (idx === -1) throw new NotFoundError(id)
  return idx
}

export function resetAgentSessions(): void {
  store = SEED.map((s) => ({ ...s }))
  transcriptStore = { ...SEED_TRANSCRIPTS }
  nextIdSeq = 100
}

export function getAgentSessionTranscript(devcontainerId: string, sessionId: string): AgentSessionTranscript {
  const idx = store.findIndex((s) => s.id === sessionId && s.devcontainer_id === devcontainerId)
  if (idx === -1) throw new NotFoundError(sessionId)

  const dcView = getDevcontainer(devcontainerId)
  const isConnected = dcView.runtime.agent_connected

  const turns = transcriptStore[sessionId]

  if (!isConnected) {
    return {
      state: 'summary_fallback',
      turns: [],
      summary_text: SESSION_SUMMARIES[sessionId] ?? null,
    }
  }

  if (turns && turns.length > 0) {
    return { state: 'has_turns', turns, summary_text: null }
  }

  return { state: 'empty', turns: [], summary_text: null }
}

export function listAgentSessions(devcontainerId: string): AgentSessionList {
  return {
    items: store
      .filter((s) => s.devcontainer_id === devcontainerId)
      .map((s) => ({ ...s })),
  }
}

export function getAgentSession(devcontainerId: string, sessionId: string): AgentSessionDetail {
  const idx = findIdx(sessionId)
  if (store[idx].devcontainer_id !== devcontainerId) throw new NotFoundError(sessionId)
  return {
    ...store[idx],
    summary_text: SESSION_SUMMARIES[sessionId] ?? null,
  }
}

export function startAgentSession(devcontainerId: string, body: AgentSessionStartBody): AgentSession {
  const ts = now()
  const session: AgentSession = {
    id: `as-mock-${String(nextIdSeq++).padStart(4, '0')}`,
    devcontainer_id: devcontainerId,
    status: 'starting',
    prompt: body.prompt,
    started_at: null,
    ended_at: null,
    last_event_at: null,
    created_at: ts,
    updated_at: ts,
  }
  store.push(session)
  return { ...session }
}

export function resumeAgentSession(devcontainerId: string, sessionId: string, body: AgentSessionResumeBody): AgentSession {
  const idx = findIdx(sessionId)
  if (store[idx].devcontainer_id !== devcontainerId) throw new NotFoundError(sessionId)
  if (!RESTING_STATUSES.has(store[idx].status)) throw new NonRestingError(sessionId)
  const otherActive = store.some(
    (s) => s.devcontainer_id === devcontainerId && s.id !== sessionId && ACTIVE_STATUSES.has(s.status),
  )
  if (otherActive) throw new OtherSessionActiveError(devcontainerId)

  const ts = now()
  store[idx] = { ...store[idx], status: 'running', ended_at: null, last_event_at: ts, updated_at: ts }

  // Append the follow-up turn so the resumed thread is visible in the transcript.
  const turns = transcriptStore[sessionId] ?? []
  transcriptStore[sessionId] = [...turns, { id: `${sessionId}-resume-${turns.length}`, role: 'user', blocks: [{ kind: 'text', text: body.prompt }], at: ts }]

  return { ...store[idx] }
}

export function stopAgentSession(devcontainerId: string, sessionId: string): AgentSession {
  const idx = findIdx(sessionId)
  if (store[idx].devcontainer_id !== devcontainerId) throw new NotFoundError(sessionId)
  const ts = now()
  store[idx] = { ...store[idx], status: 'stopped', ended_at: ts, updated_at: ts }
  return { ...store[idx] }
}

export function deleteAgentSession(devcontainerId: string, sessionId: string): void {
  const idx = findIdx(sessionId)
  if (store[idx].devcontainer_id !== devcontainerId) throw new NotFoundError(sessionId)
  if (ACTIVE_STATUSES.has(store[idx].status)) throw new ActiveSessionError(sessionId)
  store.splice(idx, 1)
}
