import { getJson, sendJson } from './client'
import type {
  AgentSession,
  AgentSessionDetail,
  AgentSessionApprovalBody,
  AgentSessionList,
  AgentSessionResumeBody,
  AgentSessionStartBody,
  AgentSessionTranscript,
  AgentSessionUserInputBody,
  ApprovalRequest,
  ApprovalRequestList,
  ApprovalStatus,
  ConfigResponse,
  Devcontainer,
  DevcontainerCreateBody,
  DevcontainerList,
  DevcontainerUpdateBody,
  DevcontainerView,
  DevcontainerViewList,
  DiagnosticsResponse,
  HealthResponse,
  InboxEvent,
  InboxEventDetail,
  InboxEventList,
  RuntimeStatus,
  SettingsResponse,
  StatusResponse,
} from './types'

const buildQuery = (params: Record<string, string | undefined>): string => {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, v)
  const s = q.toString()
  return s ? `?${s}` : ''
}

export const fetchHealth = (): Promise<HealthResponse> => getJson('/health')
export const fetchStatus = (): Promise<StatusResponse> => getJson('/status')
export const fetchConfig = (): Promise<ConfigResponse> => getJson('/config')
export const fetchDevcontainers = (): Promise<DevcontainerList> => getJson('/devcontainers')
export const fetchDevcontainerViews = (): Promise<DevcontainerViewList> => getJson('/devcontainers')
export const fetchRuntimeStatus = (): Promise<RuntimeStatus> => getJson('/runtime/status')
export const fetchSettings = (): Promise<SettingsResponse> => getJson('/settings')
export const fetchDiagnostics = (): Promise<DiagnosticsResponse> => getJson('/diagnostics')

export const createDevcontainer = (body: DevcontainerCreateBody): Promise<Devcontainer> =>
  sendJson<Devcontainer>('/devcontainers', 'POST', body) as Promise<Devcontainer>

export const fetchDevcontainer = (id: string): Promise<DevcontainerView> =>
  getJson(`/devcontainers/${encodeURIComponent(id)}`)

export const updateDevcontainer = (id: string, body: DevcontainerUpdateBody): Promise<Devcontainer> =>
  sendJson<Devcontainer>(`/devcontainers/${encodeURIComponent(id)}`, 'PATCH', body) as Promise<Devcontainer>

export const deleteDevcontainer = (id: string): Promise<void> =>
  sendJson<void>(`/devcontainers/${encodeURIComponent(id)}`, 'DELETE')

export const startDevcontainer = (id: string): Promise<Devcontainer> =>
  sendJson<Devcontainer>(`/devcontainers/${encodeURIComponent(id)}/start`, 'POST') as Promise<Devcontainer>

export const stopDevcontainer = (id: string): Promise<Devcontainer> =>
  sendJson<Devcontainer>(`/devcontainers/${encodeURIComponent(id)}/stop`, 'POST') as Promise<Devcontainer>

export const fetchAgentSessions = (devcontainerId: string): Promise<AgentSessionList> =>
  getJson(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions`)

export const fetchAgentSession = (devcontainerId: string, sessionId: string): Promise<AgentSessionDetail> =>
  getJson(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}`)

export const startAgentSession = (devcontainerId: string, body: AgentSessionStartBody): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions`, 'POST', body) as Promise<AgentSession>

export const stopAgentSession = (devcontainerId: string, sessionId: string): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/stop`, 'POST') as Promise<AgentSession>

export const resumeAgentSession = (devcontainerId: string, sessionId: string, body: AgentSessionResumeBody): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/resume`, 'POST', body) as Promise<AgentSession>

export const deleteAgentSession = (devcontainerId: string, sessionId: string): Promise<void> =>
  sendJson<void>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}`, 'DELETE')

export const fetchAgentSessionTranscript = (devcontainerId: string, sessionId: string): Promise<AgentSessionTranscript> =>
  getJson(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/transcript`)

export const sendAgentSessionUserInput = (devcontainerId: string, sessionId: string, body: AgentSessionUserInputBody): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/user-input`, 'POST', body) as Promise<AgentSession>

export const resolveAgentSessionApproval = (devcontainerId: string, sessionId: string, body: AgentSessionApprovalBody): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/approval-resolution`, 'POST', body) as Promise<AgentSession>

export const listInboxEvents = (filters?: {
  status?: string
  devcontainerId?: string
  agentSessionId?: string
}): Promise<InboxEventList> =>
  getJson(`/inbox-events${buildQuery({ status: filters?.status, devcontainer_id: filters?.devcontainerId, agent_session_id: filters?.agentSessionId })}`)

export const fetchInboxEvent = (id: string): Promise<InboxEventDetail> =>
  getJson(`/inbox-events/${encodeURIComponent(id)}`)

export const markInboxEventRead = (id: string): Promise<InboxEvent> =>
  sendJson<InboxEvent>(`/inbox-events/${encodeURIComponent(id)}/read`, 'POST') as Promise<InboxEvent>

export const resolveInboxEvent = (id: string): Promise<InboxEvent> =>
  sendJson<InboxEvent>(`/inbox-events/${encodeURIComponent(id)}/resolve`, 'POST') as Promise<InboxEvent>

export const listApprovalRequests = (filters?: {
  status?: ApprovalStatus
  devcontainerId?: string
}): Promise<ApprovalRequestList> =>
  getJson(`/approval-requests${buildQuery({ status: filters?.status, devcontainer_id: filters?.devcontainerId })}`)

export const fetchApprovalRequest = (id: string): Promise<ApprovalRequest> =>
  getJson(`/approval-requests/${encodeURIComponent(id)}`)
