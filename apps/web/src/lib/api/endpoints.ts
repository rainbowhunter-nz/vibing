import { getJson, sendJson } from './client'
import type {
  AgentSession,
  AgentSessionApprovalBody,
  AgentSessionStartBody,
  AgentSessionUserInputBody,
  ConfigResponse,
  Devcontainer,
  DevcontainerCreateBody,
  DevcontainerList,
  DevcontainerUpdateBody,
  DiagnosticsResponse,
  HealthResponse,
  SettingsResponse,
  StatusResponse,
} from './types'

export const fetchHealth = (): Promise<HealthResponse> => getJson('/health')
export const fetchStatus = (): Promise<StatusResponse> => getJson('/status')
export const fetchConfig = (): Promise<ConfigResponse> => getJson('/config')
export const fetchDevcontainers = (): Promise<DevcontainerList> => getJson('/devcontainers')
export const fetchSettings = (): Promise<SettingsResponse> => getJson('/settings')
export const fetchDiagnostics = (): Promise<DiagnosticsResponse> => getJson('/diagnostics')

export const createDevcontainer = (body: DevcontainerCreateBody): Promise<Devcontainer> =>
  sendJson<Devcontainer>('/devcontainers', 'POST', body) as Promise<Devcontainer>

export const fetchDevcontainer = (id: string): Promise<Devcontainer> =>
  getJson(`/devcontainers/${encodeURIComponent(id)}`)

export const updateDevcontainer = (id: string, body: DevcontainerUpdateBody): Promise<Devcontainer> =>
  sendJson<Devcontainer>(`/devcontainers/${encodeURIComponent(id)}`, 'PATCH', body) as Promise<Devcontainer>

export const deleteDevcontainer = (id: string): Promise<void> =>
  sendJson<void>(`/devcontainers/${encodeURIComponent(id)}`, 'DELETE')

export const startDevcontainer = (id: string): Promise<Devcontainer> =>
  sendJson<Devcontainer>(`/devcontainers/${encodeURIComponent(id)}/start`, 'POST') as Promise<Devcontainer>

export const stopDevcontainer = (id: string): Promise<Devcontainer> =>
  sendJson<Devcontainer>(`/devcontainers/${encodeURIComponent(id)}/stop`, 'POST') as Promise<Devcontainer>

export const startAgentSession = (devcontainerId: string, body: AgentSessionStartBody): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions`, 'POST', body) as Promise<AgentSession>

export const stopAgentSession = (devcontainerId: string, sessionId: string): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/stop`, 'POST') as Promise<AgentSession>

export const sendAgentSessionUserInput = (devcontainerId: string, sessionId: string, body: AgentSessionUserInputBody): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/user-input`, 'POST', body) as Promise<AgentSession>

export const resolveAgentSessionApproval = (devcontainerId: string, sessionId: string, body: AgentSessionApprovalBody): Promise<AgentSession> =>
  sendJson<AgentSession>(`/devcontainers/${encodeURIComponent(devcontainerId)}/agent-sessions/${encodeURIComponent(sessionId)}/approval-resolution`, 'POST', body) as Promise<AgentSession>
