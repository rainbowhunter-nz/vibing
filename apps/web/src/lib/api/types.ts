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

export interface Devcontainer {
  id: string
  name: string
  local_path: string
  status: string
  created_at: string
  updated_at: string
}

export interface DevcontainerList {
  items: Devcontainer[]
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

// Backend error envelope (src/vibing_api/core/errors.py).

export interface ApiErrorBody {
  code: string
  message: string
  details: unknown
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody
}
