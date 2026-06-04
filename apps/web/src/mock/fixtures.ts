// Healthy baseline fixtures — field coverage matches what the UI reads from each DTO.
import type {
  ApprovalRequestList,
  ConfigResponse,
  DevcontainerViewList,
  DiagnosticsResponse,
  HealthResponse,
  InboxEventList,
  RuntimeStatus,
  SettingsResponse,
  StatusResponse,
} from '../lib/api/types'

export const health: HealthResponse = { status: 'ok', service: 'vibing' }

export const status: StatusResponse = { status: 'ok', service: 'vibing', version: '0.0.0' }

export const config: ConfigResponse = { app_name: 'vibing', api_v1_prefix: '/api/v1' }

export const runtimeStatus: RuntimeStatus = { worker_connected: false }

export const settings: SettingsResponse = {
  backend_host: '127.0.0.1',
  backend_port: 8000,
  runtime: { docker: true, podman: null, devcontainer_cli: null, claude_code: null },
}

export const diagnostics: DiagnosticsResponse = {
  checks: [
    { id: 'docker', label: 'Docker', status: 'ok', message: null },
    { id: 'devcontainer_cli', label: 'Devcontainer CLI', status: 'unknown', message: null },
    { id: 'claude_code', label: 'Claude Code', status: 'unknown', message: null },
  ],
}

export const devcontainers: DevcontainerViewList = { items: [] }

export const inboxEvents: InboxEventList = { items: [] }

export const approvalRequests: ApprovalRequestList = { items: [] }
