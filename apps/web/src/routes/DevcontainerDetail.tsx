import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { fetchDevcontainer, fetchAgentSessions, fetchAgentSession, startAgentSession, stopAgentSession, useApiQuery, ApiError } from '../lib/api'
import type { AgentSession, DevcontainerView } from '../lib/api/types'
import { formatRelativeTime } from '../lib/time'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'

const ACTIVE_STATUSES = new Set<string>(['starting', 'running', 'waiting_for_approval'])

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-emerald-100 text-emerald-800'
    case 'starting':
    case 'stopping':
      return 'bg-accent-bg text-accent'
    case 'error':
      return 'bg-red-100 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function agentSessionBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-emerald-100 text-emerald-800'
    case 'starting':
    case 'waiting_for_approval':
      return 'bg-accent-bg text-accent'
    case 'failed':
      return 'bg-red-100 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 border-b border-border px-4 py-3">
      <span className="w-28 shrink-0 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">{label}</span>
      <span className="text-[13px] text-text">{children}</span>
    </div>
  )
}

function DevcontainerInfo({ dc }: { dc: DevcontainerView }) {
  return (
    <div className="px-4 pt-4">
      <h2 className="mb-4 text-base font-semibold text-text">{dc.name}</h2>
      <div className="rounded-md border border-border">
        <Row label="Local path">{dc.local_path}</Row>
        <Row label="Status">
          <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', statusBadgeClass(dc.status))}>
            {dc.status}
          </span>
        </Row>
        <Row label="Created">{dc.created_at}</Row>
        <Row label="Updated">{dc.updated_at}</Row>
      </div>
    </div>
  )
}

function SessionControls({
  dc,
  sessions,
  onSessionChange,
}: {
  dc: DevcontainerView
  sessions: AgentSession[]
  onSessionChange: () => void
}) {
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)

  const activeSession = sessions.find((s) => ACTIVE_STATUSES.has(s.status)) ?? null
  const hasActive = activeSession !== null
  const agentConnected = dc.runtime.agent_connected

  const startDisabled = busy || !agentConnected || hasActive || !prompt.trim()
  const stopDisabled = busy || !agentConnected

  const helperText = !agentConnected
    ? 'Agent not connected'
    : hasActive
      ? 'A session is already active'
      : null

  async function handleStart() {
    setBusy(true)
    try {
      await startAgentSession(dc.id, { prompt })
      setPrompt('')
      onSessionChange()
    } finally {
      setBusy(false)
    }
  }

  async function handleStop() {
    if (!activeSession) return
    setBusy(true)
    try {
      await stopAgentSession(dc.id, activeSession.id)
      onSessionChange()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="px-4 pt-6">
      <h3 className="mb-3 text-sm font-semibold text-text">Start Agent Session</h3>
      <div className="space-y-2">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter a prompt…"
          disabled={!agentConnected || hasActive || busy}
          rows={3}
          className="w-full resize-none rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-text placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
        />
        <div className="flex items-center gap-2">
          <button
            onClick={handleStart}
            disabled={startDisabled}
            className="rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-white disabled:opacity-40"
          >
            Start
          </button>
          {hasActive && (
            <button
              onClick={handleStop}
              disabled={stopDisabled}
              className="rounded-md border border-border px-3 py-1.5 text-[13px] font-medium text-text disabled:opacity-40"
            >
              Stop
            </button>
          )}
          {helperText && (
            <span className="text-[12px] text-text-muted">{helperText}</span>
          )}
        </div>
      </div>
    </div>
  )
}

function SessionRow({
  session,
  selected,
  onSelect,
}: {
  session: AgentSession
  selected: boolean
  onSelect: (id: string) => void
}) {
  return (
    <button
      onClick={() => onSelect(session.id)}
      className={cn(
        'flex w-full items-center gap-3 border-b border-border px-4 py-2.5 text-left last:border-b-0',
        selected ? 'border-l-[3px] border-l-accent bg-accent-bg/40 pl-[13px]' : 'hover:bg-surface-muted',
      )}
    >
      <span className="font-mono text-[12px] text-text-muted">{session.id.slice(0, 8)}</span>
      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', agentSessionBadgeClass(session.status))}>
        {session.status}
      </span>
      {session.prompt && (
        <span className="min-w-0 flex-1 truncate text-[12px] text-text-muted">{session.prompt}</span>
      )}
    </button>
  )
}

function ConversationBubble({ role, children }: { role: 'user' | 'agent'; children: React.ReactNode }) {
  const isUser = role === 'user'
  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-[10px] px-3 py-2.5 text-[13px] leading-relaxed',
          isUser ? 'bg-accent text-white' : 'bg-surface-muted text-text',
        )}
      >
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.05em] opacity-70">
          {isUser ? 'You' : 'Agent'}
        </div>
        {children}
      </div>
    </div>
  )
}

function SessionDetailPanel({
  devcontainerId,
  sessionId,
  onClose,
}: {
  devcontainerId: string
  sessionId: string
  onClose: () => void
}) {
  const { state, refetch } = useApiQuery(
    () => fetchAgentSession(devcontainerId, sessionId),
    [devcontainerId, sessionId],
  )
  const { register } = useSseInvalidation()

  useEffect(() => register('agent_sessions', refetch), [register, refetch])

  if (state.kind === 'loading') {
    return (
      <div className="px-4 pt-4">
        <div className="rounded-md border border-border p-4 text-[13px] text-text-muted">Loading session…</div>
      </div>
    )
  }

  if (state.kind === 'error') {
    if (state.error instanceof ApiError && state.error.code === 'AGENT_SESSION_NOT_FOUND') {
      return (
        <div className="px-4 pt-4">
          <ErrorState title="Session not found" helper="This session doesn't exist or has been removed." />
        </div>
      )
    }
    return (
      <div className="px-4 pt-4">
        <ErrorState {...loadError('session')} />
      </div>
    )
  }

  const session = state.data
  const isActive = ACTIVE_STATUSES.has(session.status)

  return (
    <div className="px-4 pt-4">
      <div className="rounded-md border border-border">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[12px] text-text-muted">{session.id.slice(0, 8)}</span>
            <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', agentSessionBadgeClass(session.status))}>
              {session.status}
            </span>
          </div>
          <button
            onClick={onClose}
            title="Close"
            className="flex h-7 w-7 items-center justify-center rounded-[5px] text-text-muted hover:bg-surface-muted"
          >
            ✕
          </button>
        </div>

        <div className="space-y-3 px-4 py-4">
          {session.prompt && <ConversationBubble role="user">{session.prompt}</ConversationBubble>}

          {session.summary_text ? (
            <ConversationBubble role="agent">{session.summary_text}</ConversationBubble>
          ) : isActive ? (
            <p className="text-[13px] text-text-muted">Session in progress…</p>
          ) : (
            <p className="text-[13px] text-text-muted">No output recorded.</p>
          )}
        </div>

        <div className="border-t border-border px-4 py-2 text-[11px] text-text-muted">
          {session.started_at && <span>Started {formatRelativeTime(session.started_at)}</span>}
          {session.ended_at && <span> · Ended {formatRelativeTime(session.ended_at)}</span>}
        </div>
      </div>
    </div>
  )
}

function AgentSessionsList({
  sessions,
  selectedId,
  onSelect,
  devcontainerId,
}: {
  sessions: AgentSession[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  devcontainerId: string
}) {
  return (
    <div className="px-4 pt-6">
      <h3 className="mb-3 text-sm font-semibold text-text">Agent Sessions</h3>
      {sessions.length === 0 ? (
        <p className="text-[13px] text-text-muted">No agent sessions</p>
      ) : (
        <>
          <div className="rounded-md border border-border">
            {[...sessions].reverse().map((s) => (
              <SessionRow
                key={s.id}
                session={s}
                selected={s.id === selectedId}
                onSelect={(id) => onSelect(selectedId === id ? null : id)}
              />
            ))}
          </div>
          {selectedId && (
            <SessionDetailPanel
              devcontainerId={devcontainerId}
              sessionId={selectedId}
              onClose={() => onSelect(null)}
            />
          )}
        </>
      )}
    </div>
  )
}

function errorElement(error: unknown) {
  if (error instanceof ApiError && error.code === 'DEVCONTAINER_NOT_FOUND') {
    return (
      <ErrorState
        title="Devcontainer not found"
        helper="This devcontainer doesn't exist or has been deleted."
      />
    )
  }
  return <ErrorState {...loadError('devcontainer')} />
}

export function DevcontainerDetail() {
  const { id } = useParams<{ id: string }>()
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const { register } = useSseInvalidation()

  const { state, refetch } = useApiQuery(() => fetchDevcontainer(id!), [id])
  const { state: sessionsState, refetch: refetchSessions } = useApiQuery(
    () => fetchAgentSessions(id!),
    [id],
  )

  useEffect(() => register('devcontainers', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetchSessions), [register, refetchSessions])

  return (
    <>
      <PageHeader title="Devcontainer" crumbs="Detail" />
      <div className="flex-1 overflow-auto">
        <QueryBoundary state={state} error={errorElement(state.kind === 'error' ? state.error : null)}>
          {(dc) => (
            <>
              <DevcontainerInfo dc={dc} />
              {sessionsState.kind === 'ready' && (
                <>
                  <SessionControls dc={dc} sessions={sessionsState.data.items} onSessionChange={refetchSessions} />
                  <AgentSessionsList
                    sessions={sessionsState.data.items}
                    selectedId={selectedSessionId}
                    onSelect={setSelectedSessionId}
                    devcontainerId={dc.id}
                  />
                </>
              )}
            </>
          )}
        </QueryBoundary>
      </div>
    </>
  )
}
