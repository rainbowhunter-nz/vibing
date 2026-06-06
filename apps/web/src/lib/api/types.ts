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

export type DevcontainerStatus = 'created' | 'starting' | 'running' | 'stopping' | 'stopped' | 'error'

export interface Devcontainer {
  id: string
  name: string
  local_path: string
  status: DevcontainerStatus
  created_at: string
  updated_at: string
}

export interface RuntimeConnection {
  worker_connected: boolean
  agent_connected: boolean
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
  status?: DevcontainerStatus
}

export interface DevcontainerList {
  items: Devcontainer[]
}

export interface DevcontainerViewList {
  items: DevcontainerView[]
}

export interface RuntimeStatus {
  worker_connected: boolean
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

export type AgentSessionStatus =
  | 'starting'
  | 'running'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'stopped'

export interface AgentSession {
  id: string
  devcontainer_id: string
  status: AgentSessionStatus
  prompt: string | null
  started_at: string | null
  ended_at: string | null
  last_event_at: string | null
  created_at: string
  updated_at: string
}

export interface AgentSessionDetail extends AgentSession {
  summary_text: string | null
}

export interface AgentSessionList {
  items: AgentSession[]
}

export interface AgentSessionStartBody {
  prompt: string
}

export interface AgentSessionResumeBody {
  prompt: string
}

export interface AgentSessionUserInputBody {
  inbox_event_id: string
  text: string
}

export type ApprovalResolution = 'approved' | 'rejected'

export interface AgentSessionApprovalBody {
  approval_request_id: string
  resolution: ApprovalResolution
}

export type InboxEventType = 'question' | 'approval_request' | 'completion' | 'failure'

export type InboxEventStatus = 'unread' | 'read' | 'resolved'

export interface InboxEvent {
  id: string
  devcontainer_id: string
  agent_session_id: string | null
  approval_request_id: string | null
  event_type: InboxEventType
  status: InboxEventStatus
  created_at: string
  updated_at: string
}

export interface InboxEventDetail extends InboxEvent {
  content: string | null
  devcontainer: Devcontainer
  agent_session: AgentSession | null
  approval_request: ApprovalRequest | null
}

export interface InboxEventList {
  items: InboxEvent[]
}

export type ApprovalStatus = 'pending' | 'approved' | 'rejected'

export interface ApprovalRequest {
  id: string
  devcontainer_id: string
  agent_session_id: string
  status: ApprovalStatus
  requested_action: string
  created_at: string
  decided_at: string | null
}

export interface ApprovalRequestList {
  items: ApprovalRequest[]
}

export interface TranscriptTextBlock {
  kind: 'text'
  text: string
}

export interface TranscriptToolUseBlock {
  kind: 'tool_use'
  name: string
  summary: string
}

export type TranscriptBlock = TranscriptTextBlock | TranscriptToolUseBlock

export interface TranscriptTurn {
  role: 'user' | 'assistant'
  blocks: TranscriptBlock[]
  at: string
}

export type TranscriptState = 'has_turns' | 'empty' | 'summary_fallback' | 'error'

export interface AgentSessionTranscript {
  state: TranscriptState
  turns: TranscriptTurn[]
  summary_text: string | null
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
