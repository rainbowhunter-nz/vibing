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
  // Claude's per-message uuid (ADR-0010): the stable key the live reducer merges on.
  id: string
  role: 'user' | 'assistant'
  blocks: TranscriptBlock[]
  at: string
}

export type TranscriptState = 'has_turns' | 'empty' | 'summary_fallback' | 'error'

// Per-session live turn-deltas (ADR-0010), relayed over the per-session SSE stream.
export interface RunStartedDelta {
  kind: 'run_started'
}

export interface TextDelta {
  kind: 'text'
  turn_id: string
  role: 'assistant'
  text: string
}

export interface RunEndedDelta {
  kind: 'run_ended'
}

export interface ToolUseDelta {
  kind: 'tool_use'
  turn_id: string
  name: string
  summary: string
}

export type TurnDelta = RunStartedDelta | TextDelta | RunEndedDelta | ToolUseDelta

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
