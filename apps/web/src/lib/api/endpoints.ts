import { getJson, sendJson } from './client'
import type {
  ConfigResponse,
  DiagnosticsResponse,
  HealthResponse,
  SettingsResponse,
  StatusResponse,
  WorkspaceList,
} from './types'

export const fetchHealth = (): Promise<HealthResponse> => getJson('/health')
export const fetchStatus = (): Promise<StatusResponse> => getJson('/status')
export const fetchConfig = (): Promise<ConfigResponse> => getJson('/config')
export const fetchWorkspaces = (): Promise<WorkspaceList> => getJson('/workspaces')
export const fetchSettings = (): Promise<SettingsResponse> => getJson('/settings')
export const fetchDiagnostics = (): Promise<DiagnosticsResponse> => getJson('/diagnostics')

export const deleteWorkspace = (id: string): Promise<void> =>
  sendJson<void>(`/workspaces/${encodeURIComponent(id)}`, 'DELETE')
