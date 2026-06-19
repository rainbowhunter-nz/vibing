import { getJson, sendJson } from './client'
import type {
  ConfigResponse,
  Devcontainer,
  DevcontainerCreateBody,
  DevcontainerList,
  DevcontainerUpdateBody,
  DevcontainerView,
  DevcontainerViewList,
  DiagnosticsResponse,
  HealthResponse,
  HarnessStatus,
  HarnessStatusList,
  SettingsResponse,
  StatusResponse,
} from './types'

export const fetchHealth = (): Promise<HealthResponse> => getJson('/health')
export const fetchStatus = (): Promise<StatusResponse> => getJson('/status')
export const fetchConfig = (): Promise<ConfigResponse> => getJson('/config')
export const fetchDevcontainers = (): Promise<DevcontainerList> => getJson('/devcontainers')
export const fetchDevcontainerViews = (): Promise<DevcontainerViewList> => getJson('/devcontainers')
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


export const fetchHarnesses = (devcontainerId: string): Promise<HarnessStatusList> =>
  getJson(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses`)

export const authenticateHarness = (devcontainerId: string, name: string): Promise<HarnessStatus> =>
  sendJson<HarnessStatus>(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/${encodeURIComponent(name)}/authenticate`, 'POST') as Promise<HarnessStatus>
