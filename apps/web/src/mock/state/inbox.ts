import type {
  Devcontainer,
  AgentSession,
  ApprovalRequest,
  InboxEvent,
  InboxEventDetail,
  InboxEventList,
} from '../../lib/api/types'

// Shared devcontainers for inbox seeds
const DC1: Devcontainer = {
  id: 'dc-seed-0001',
  name: 'my-webapp',
  local_path: '/home/dev/my-webapp',
  status: 'running',
  created_at: '2024-01-10T08:00:00.000Z',
  updated_at: '2024-01-15T10:00:00.000Z',
}

const DC2: Devcontainer = {
  id: 'dc-seed-0002',
  name: 'api-service',
  local_path: '/home/dev/api-service',
  status: 'stopped',
  created_at: '2024-01-11T09:00:00.000Z',
  updated_at: '2024-01-14T14:30:00.000Z',
}

const SESSION1: AgentSession = {
  id: 'as-seed-0001',
  devcontainer_id: 'dc-seed-0001',
  status: 'waiting_for_approval',
  started_at: '2024-01-15T09:00:00.000Z',
  ended_at: null,
  last_event_at: '2024-01-15T09:55:00.000Z',
  created_at: '2024-01-15T09:00:00.000Z',
  updated_at: '2024-01-15T09:55:00.000Z',
}

const SESSION2: AgentSession = {
  id: 'as-seed-0002',
  devcontainer_id: 'dc-seed-0002',
  status: 'running',
  started_at: '2024-01-15T10:00:00.000Z',
  ended_at: null,
  last_event_at: '2024-01-15T10:30:00.000Z',
  created_at: '2024-01-15T10:00:00.000Z',
  updated_at: '2024-01-15T10:30:00.000Z',
}

const SESSION3: AgentSession = {
  id: 'as-seed-0003',
  devcontainer_id: 'dc-seed-0002',
  status: 'failed',
  started_at: '2024-01-14T08:00:00.000Z',
  ended_at: '2024-01-14T08:45:00.000Z',
  last_event_at: '2024-01-14T08:45:00.000Z',
  created_at: '2024-01-14T08:00:00.000Z',
  updated_at: '2024-01-14T08:45:00.000Z',
}

const SESSION4: AgentSession = {
  id: 'as-seed-0004',
  devcontainer_id: 'dc-seed-0001',
  status: 'completed',
  started_at: '2024-01-13T12:00:00.000Z',
  ended_at: '2024-01-13T12:30:00.000Z',
  last_event_at: '2024-01-13T12:30:00.000Z',
  created_at: '2024-01-13T12:00:00.000Z',
  updated_at: '2024-01-13T12:30:00.000Z',
}

const APPROVAL1: ApprovalRequest = {
  id: 'ar-seed-0001',
  devcontainer_id: 'dc-seed-0001',
  agent_session_id: 'as-seed-0001',
  status: 'pending',
  requested_action: 'run: pnpm migrate --env production',
  created_at: '2024-01-15T09:55:00.000Z',
  decided_at: null,
}

// Fixed seed: covers all 4 event_types, spread of statuses
const SEED: InboxEventDetail[] = [
  {
    id: 'ie-seed-0001',
    devcontainer_id: 'dc-seed-0002',
    agent_session_id: 'as-seed-0002',
    approval_request_id: null,
    event_type: 'question',
    status: 'unread',
    created_at: '2024-01-15T10:30:00.000Z',
    updated_at: '2024-01-15T10:30:00.000Z',
    content: 'Should I use Redis or in-memory caching for this feature?',
    devcontainer: DC2,
    agent_session: SESSION2,
    approval_request: null,
  },
  {
    id: 'ie-seed-0002',
    devcontainer_id: 'dc-seed-0001',
    agent_session_id: 'as-seed-0001',
    approval_request_id: 'ar-seed-0001',
    event_type: 'approval_request',
    status: 'unread',
    created_at: '2024-01-15T09:55:00.000Z',
    updated_at: '2024-01-15T09:55:00.000Z',
    content: null,
    devcontainer: DC1,
    agent_session: SESSION1,
    approval_request: APPROVAL1,
  },
  {
    id: 'ie-seed-0003',
    devcontainer_id: 'dc-seed-0002',
    agent_session_id: 'as-seed-0003',
    approval_request_id: null,
    event_type: 'failure',
    status: 'unread',
    created_at: '2024-01-14T08:45:00.000Z',
    updated_at: '2024-01-14T08:45:00.000Z',
    content: 'Agent session terminated unexpectedly: process exited with code 1.',
    devcontainer: DC2,
    agent_session: SESSION3,
    approval_request: null,
  },
  {
    id: 'ie-seed-0004',
    devcontainer_id: 'dc-seed-0001',
    agent_session_id: 'as-seed-0004',
    approval_request_id: null,
    event_type: 'completion',
    status: 'resolved',
    created_at: '2024-01-13T12:30:00.000Z',
    updated_at: '2024-01-13T12:35:00.000Z',
    content: 'Task completed successfully. All tests pass.',
    devcontainer: DC1,
    agent_session: SESSION4,
    approval_request: null,
  },
]

let store: InboxEventDetail[] = SEED.map((e) => deepCopy(e))

function deepCopy(e: InboxEventDetail): InboxEventDetail {
  return {
    ...e,
    devcontainer: { ...e.devcontainer },
    agent_session: e.agent_session ? { ...e.agent_session } : null,
    approval_request: e.approval_request ? { ...e.approval_request } : null,
  }
}

function toInboxEvent(detail: InboxEventDetail): InboxEvent {
  return {
    id: detail.id,
    devcontainer_id: detail.devcontainer_id,
    agent_session_id: detail.agent_session_id,
    approval_request_id: detail.approval_request_id,
    event_type: detail.event_type,
    status: detail.status,
    created_at: detail.created_at,
    updated_at: detail.updated_at,
  }
}

function now(): string {
  return new Date().toISOString()
}

export class NotFoundError extends Error {
  readonly code = 'INBOX_EVENT_NOT_FOUND'
  constructor(id: string) {
    super(`Inbox event not found: ${id}`)
  }
}

function findIdx(id: string): number {
  const idx = store.findIndex((e) => e.id === id)
  if (idx === -1) throw new NotFoundError(id)
  return idx
}

export function resetInbox(): void {
  store = SEED.map((e) => deepCopy(e))
}

export function listInboxEvents(): InboxEventList {
  return { items: store.map(toInboxEvent) }
}

export function getInboxEvent(id: string): InboxEventDetail {
  return deepCopy(store[findIdx(id)])
}

export function markInboxEventRead(id: string): InboxEvent {
  const idx = findIdx(id)
  store[idx] = { ...store[idx], status: 'read', updated_at: now() }
  return toInboxEvent(store[idx])
}

export function resolveInboxEvent(id: string): InboxEvent {
  const idx = findIdx(id)
  store[idx] = { ...store[idx], status: 'resolved', updated_at: now() }
  return toInboxEvent(store[idx])
}
