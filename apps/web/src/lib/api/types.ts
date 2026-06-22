// Backend response shapes (src/vibing_api/api/routes/*).

export interface HealthResponse {
  status: string
  service: string
}

export interface StatusResponse {
  status: string
  service: string
  version: string
}

export interface ConfigResponse {
  app_name: string
  api_v1_prefix: string
}

export type DevcontainerStatus = 'starting' | 'running' | 'stopping' | 'stopped' | 'error'
export type DevcontainerSource = 'manual' | 'discovered'

export interface Devcontainer {
  id: string
  name: string
  local_path: string
  status: DevcontainerStatus
  source: DevcontainerSource
  created_at: string | null
  updated_at: string | null
}

export type RuntimeState = 'connected' | 'launching' | 'disconnected'

export interface RuntimeConnection {
  state: RuntimeState
}

export interface RuntimeLogs {
  content: string | null
}

export interface DevcontainerView extends Devcontainer {
  runtime: RuntimeConnection
}

export interface DevcontainerCreateBody {
  name: string
  local_path: string
}

export interface DevcontainerUpdateBody {
  name?: string
}

export interface DevcontainerList {
  items: Devcontainer[]
}

export interface DevcontainerViewList {
  items: DevcontainerView[]
}

export interface RuntimeDetection {
  docker: boolean | null
  podman: boolean | null
  devcontainer_cli: boolean | null
  claude_code: boolean | null
}

export interface SettingsResponse {
  backend_host: string
  backend_port: number
  runtime: RuntimeDetection
}

export type DiagnosticStatus = 'ok' | 'fail' | 'unknown'

export interface DiagnosticCheck {
  id: string
  label: string
  status: DiagnosticStatus
  message: string | null
}

export interface DiagnosticsResponse {
  checks: DiagnosticCheck[]
}

// Coding-harness status (runtime HarnessStatus, ADR-0012).
export interface HarnessStatus {
  name: string
  installed: boolean
  authenticated: boolean
}

export interface HarnessStatusList {
  items: HarnessStatus[]
  known: boolean
}

// Delegated runs (runtime DelegatedRunManager, ADR-0013).
export type DelegatedRunStatus = 'running' | 'completed' | 'failed' | 'stopped'

export interface DelegatedRun {
  run_id: string
  harness: string
  model: string
  status: DelegatedRunStatus
  result: string | null
  error: Record<string, unknown> | null
  started_at: string
}

export interface DelegatedRunList {
  items: DelegatedRun[]
}

// Backend error envelope (src/vibing_api/core/errors.py).

export interface ApiErrorBody {
  code: string
  message: string
  details: unknown
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody
}
