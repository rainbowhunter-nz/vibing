export interface HealthResponse {
  status: string
  service: string
}

export interface ConfigResponse {
  app_name: string
  api_v1_prefix: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    throw new Error(`${path} ${res.status}`)
  }
  return (await res.json()) as T
}

async function sendJson<T>(path: string, method: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`${path} ${res.status}`)
  }
  return (await res.json()) as T
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/v1/health')
}

export function fetchConfig(): Promise<ConfigResponse> {
  return getJson<ConfigResponse>('/api/v1/config')
}

export interface Workspace {
  id: string
  name: string
  local_path: string
  status: string
  created_at: string
  updated_at: string
}

interface WorkspaceList {
  items: Workspace[]
}

export function fetchWorkspaces(): Promise<WorkspaceList> {
  return getJson<WorkspaceList>('/api/v1/workspaces')
}

export interface RuntimeDetection {
  docker: boolean | null
  podman: boolean | null
  devcontainer_cli: boolean | null
  claude_code: boolean | null
}

export interface SettingsResponse {
  workspace_storage_location: string
  backend_host: string
  backend_port: number
  editor_preference: string | null
  notifications_enabled: boolean | null
  runtime: RuntimeDetection
}

export function fetchSettings(): Promise<SettingsResponse> {
  return getJson<SettingsResponse>('/api/v1/settings')
}

export function updateSettings(patch: {
  workspace_storage_location: string
}): Promise<SettingsResponse> {
  return sendJson<SettingsResponse>('/api/v1/settings', 'PATCH', patch)
}
