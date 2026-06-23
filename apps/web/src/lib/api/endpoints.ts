import { ApiError, getJson, sendJson, streamText } from './client'
import type {
  ConfigResponse,
  DelegatedRunList,
  Devcontainer,
  DevcontainerCreateBody,
  DevcontainerList,
  DevcontainerUpdateBody,
  DevcontainerView,
  DevcontainerViewList,
  DiagnosticsResponse,
  HealthResponse,
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

export const injectRuntime = (id: string): Promise<void> =>
  sendJson<void>(`/devcontainers/${encodeURIComponent(id)}/inject-runtime`, 'POST')

export const stopRuntime = (id: string): Promise<void> =>
  sendJson<void>(`/devcontainers/${encodeURIComponent(id)}/stop-runtime`, 'POST')

export async function streamRuntimeLogs(
  id: string,
  signal: AbortSignal,
  onChunk: (text: string) => void,
): Promise<void> {
  const res = await fetch(`/api/v1/devcontainers/${encodeURIComponent(id)}/runtime-logs/stream`, { signal })
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, 'HTTP_ERROR', `runtime log stream failed (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
  const tail = decoder.decode()
  if (tail) onChunk(tail)
}

export const removeContainer = (id: string): Promise<void> =>
  sendJson<void>(`/devcontainers/${encodeURIComponent(id)}/remove-container`, 'POST')

export const fetchHarnesses = (devcontainerId: string): Promise<HarnessStatusList> =>
  getJson(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses`)

export const installHarness = (devcontainerId: string, name: string): Promise<void> =>
  streamText(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/${encodeURIComponent(name)}/install`)

export const authenticateHarness = (devcontainerId: string, name: string): Promise<void> =>
  streamText(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/${encodeURIComponent(name)}/authenticate`)

export const refreshHarnesses = (devcontainerId: string): Promise<HarnessStatusList> =>
  sendJson<HarnessStatusList>(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/refresh`, 'POST') as Promise<HarnessStatusList>

export const fetchDelegatedRuns = (devcontainerId: string): Promise<DelegatedRunList> =>
  getJson(`/devcontainers/${encodeURIComponent(devcontainerId)}/delegated-runs`)
