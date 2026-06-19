import { API_BASE, getJson, sendJson } from './client'
import type {
  AgentSession,
  AgentSessionDetail,
  AgentSessionList,
  AgentSessionResumeBody,
  AgentSessionStartBody,
  AgentSessionTranscript,
  ConfigResponse,
  Devcontainer,
  DevcontainerCreateBody,
  DevcontainerList,
  DevcontainerUpdateBody,
  DevcontainerView,
  DevcontainerViewList,
  DiagnosticsResponse,
  HealthResponse,
  RuntimeStatus,
  SettingsResponse,
  StatusResponse,
} from './types'

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

// Per-session live turn-delta stream (ADR-0010). A SEPARATE EventSource from the global
// invalidation coordinator; open only while a session is active, close when it rests.
export const openAgentSessionStream = (devcontainerId: string, sessionId: string): EventSource =>
  new EventSource(`${API_BASE}/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/stream`)
