import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { fetchDevcontainer, fetchAgentSessions, fetchAgentSession, fetchAgentSessionTranscript, startAgentSession, stopAgentSession, resumeAgentSession, deleteAgentSession, listInboxEvents, useApiQuery, ApiError } from '../lib/api'
import type { AgentSession, DevcontainerView, TranscriptBlock, TranscriptTurn } from '../lib/api/types'
import { formatRelativeTime } from '../lib/time'
import { useSseInvalidation } from '../lib/events'
import { liveOnlyTurns, mergeTurns, useSessionStream } from '../lib/stream'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'
import { shouldStick, isWorkingIndicatorVisible } from '../lib/chat/chatHelpers'
import { InlineInterventionCard } from '../lib/intervention'
import { isBlocking } from './inboxViews'

const ACTIVE_STATUSES = new Set<string>(['starting', 'running', 'waiting_for_approval'])
const RESTING_STATUSES = new Set<string>(['completed', 'failed', 'stopped'])

const trashIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
)

const chevronLeftIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="15 18 9 12 15 6" />
  </svg>
)

const chevronRightIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="9 18 15 12 9 6" />
  </svg>
)

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

function InfoField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-text-muted">{label}</div>
      <div className="mt-0.5 truncate text-[13px] text-text">{children}</div>
    </div>
  )
}

function DevcontainerInfo({ dc }: { dc: DevcontainerView }) {
  const [expanded, setExpanded] = useState(false)
  const agentOk = dc.runtime.agent_connected

  return (
    <div className="shrink-0 border-b border-border bg-surface-rail px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="min-w-0 truncate text-[14px] font-semibold text-text">{dc.name}</span>
        <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium', statusBadgeClass(dc.status))}>
          {dc.status}
        </span>
        <span
          className={cn(
            'shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium',
            agentOk ? 'bg-emerald-100 text-emerald-800' : 'bg-surface-muted text-text-muted',
          )}
        >
          {agentOk ? 'agent connected' : 'agent offline'}
        </span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="ml-auto shrink-0 text-[11px] text-text-muted hover:text-text"
        >
          {expanded ? '▾' : '▸'} details
        </button>
      </div>
      {expanded && (
        <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-2 border-t border-border pt-3">
          <InfoField label="Local path">{dc.local_path}</InfoField>
          <InfoField label="Created">{formatRelativeTime(dc.created_at)}</InfoField>
          <InfoField label="Updated">{formatRelativeTime(dc.updated_at)}</InfoField>
        </div>
      )}
    </div>
  )
}

function SessionRow({
  session,
  selected,
  onSelect,
  onDelete,
  deleting,
}: {
  session: AgentSession
  selected: boolean
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  deleting: boolean
}) {
  const isActive = ACTIVE_STATUSES.has(session.status)

  return (
    <div
      className={cn(
        'border-b border-border last:border-b-0',
        selected ? 'border-l-[3px] border-l-accent bg-accent-bg/40' : 'hover:bg-surface-muted',
      )}
    >
      <div className="flex min-w-0 items-start gap-1">
        <button
          onClick={() => onSelect(session.id)}
          className={cn('flex min-w-0 flex-1 flex-col gap-1 py-2.5 text-left', isActive ? 'px-4' : 'pl-4 pr-2')}
        >
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 font-mono text-[12px] text-text-muted">{session.id.slice(0, 8)}</span>
            <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium', agentSessionBadgeClass(session.status))}>
              {session.status}
            </span>
          </div>
          {session.prompt && (
            <span className="truncate text-[12px] text-text">{session.prompt}</span>
          )}
        </button>
        {!isActive && (
          <button
            title="Delete"
            disabled={deleting}
            onClick={() => onDelete(session.id)}
            className={cn(
              'mr-1 mt-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-[5px]',
              deleting
                ? 'cursor-not-allowed text-bad opacity-[0.4]'
                : 'cursor-pointer text-bad hover:bg-surface-muted',
            )}
          >
            {trashIcon}
          </button>
        )}
      </div>
    </div>
  )
}

function ConversationBubble({
  role,
  sending = false,
  children,
}: {
  role: 'user' | 'agent'
  sending?: boolean
  children: React.ReactNode
}) {
  const isUser = role === 'user'
  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[min(85%,42rem)] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed shadow-sm',
          isUser ? 'bg-accent text-white' : 'bg-surface-muted text-text ring-1 ring-border/60',
          sending && 'opacity-70',
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

function WorkingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="rounded-2xl bg-surface-muted px-3.5 py-2.5 text-[13px] text-text-muted ring-1 ring-border/60">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.05em] opacity-70">Agent</div>
        <span className="inline-flex items-center gap-1">
          Working
          <span className="inline-flex gap-0.5" aria-hidden>
            <span className="h-1 w-1 animate-bounce rounded-full bg-text-muted [animation-delay:0ms]" />
            <span className="h-1 w-1 animate-bounce rounded-full bg-text-muted [animation-delay:150ms]" />
            <span className="h-1 w-1 animate-bounce rounded-full bg-text-muted [animation-delay:300ms]" />
          </span>
        </span>
      </div>
    </div>
  )
}

function ToolUsePill({ name, summary }: { name: string; summary: string }) {
  return (
    <span className="mr-1 mt-1 inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-[11px] font-medium text-text-muted ring-1 ring-border">
      <span className="font-semibold text-text">{name}</span>
      <span>{summary}</span>
    </span>
  )
}

function BlockContent({ blocks }: { blocks: TranscriptBlock[] }) {
  return (
    <div className="space-y-1">
      {blocks.map((block, i) =>
        block.kind === 'tool_use' ? (
          <div key={i}>
            <ToolUsePill name={block.name} summary={block.summary} />
          </div>
        ) : (
          <p key={i}>{block.text}</p>
        ),
      )}
    </div>
  )
}

function countMatchingUserTurns(turns: TranscriptTurn[], text: string): number {
  return turns.filter(
    (t) => t.role === 'user' && t.blocks.some((b) => b.kind === 'text' && b.text.trim() === text),
  ).length
}

// ---------------------------------------------------------------------------
// Unified composer — handles start / resume / active-stop / disabled modes
// ---------------------------------------------------------------------------

type ComposerMode =
  | { kind: 'start' }
  | { kind: 'resume'; sessionId: string }
  | { kind: 'active'; sessionId: string }
  | { kind: 'disabled'; reason: string }

function resolveComposerMode(
  dc: DevcontainerView,
  sessions: AgentSession[],
  selectedId: string | null,
): ComposerMode {
  const activeSession = sessions.find((s) => ACTIVE_STATUSES.has(s.status)) ?? null
  const agentConnected = dc.runtime.agent_connected

  if (activeSession) {
    return { kind: 'active', sessionId: activeSession.id }
  }

  if (!agentConnected) {
    return { kind: 'disabled', reason: 'Agent not connected' }
  }

  const selected = selectedId ? sessions.find((s) => s.id === selectedId) ?? null : null
  if (selected && RESTING_STATUSES.has(selected.status)) {
    if (dc.status !== 'running') {
      return { kind: 'disabled', reason: 'Start the devcontainer to continue' }
    }
    return { kind: 'resume', sessionId: selected.id }
  }

  return { kind: 'start' }
}

function ChatComposer({
  dc,
  mode,
  onAction,
  onOptimisticSend,
}: {
  dc: DevcontainerView
  mode: ComposerMode
  onAction: (sessionId?: string) => void
  onOptimisticSend: (text: string | null) => void
}) {
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)

  const isActive = mode.kind === 'active'
  const isDisabled = mode.kind === 'disabled'
  const textareaDisabled = busy || isActive || isDisabled

  const placeholder = mode.kind === 'resume' ? 'Send a follow-up…' : 'Message the agent…'
  const submitLabel = mode.kind === 'resume' ? 'Send' : 'Start chat'
  const helperText = isDisabled ? mode.reason : null

  async function handleSubmit() {
    if (!prompt.trim() || textareaDisabled) return
    const text = prompt.trim()
    setPrompt('')
    onOptimisticSend(text)
    setBusy(true)
    try {
      if (mode.kind === 'start') {
        const session = await startAgentSession(dc.id, { prompt: text })
        onAction(session.id)
      } else if (mode.kind === 'resume') {
        await resumeAgentSession(dc.id, mode.sessionId, { prompt: text })
        onAction(mode.sessionId)
      }
    } catch {
      onOptimisticSend(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleStop() {
    if (mode.kind !== 'active') return
    setBusy(true)
    try {
      await stopAgentSession(dc.id, mode.sessionId)
      onAction(mode.sessionId)
    } finally {
      setBusy(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSubmit()
    }
  }

  return (
    <div className="shrink-0 border-t border-border bg-surface px-4 py-3">
      <div className="mx-auto flex max-w-3xl flex-col gap-2">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={textareaDisabled}
          rows={2}
          className="w-full resize-none rounded-xl border border-border bg-bg px-3.5 py-2.5 text-[13px] text-text placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
        />
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-text-subtle">
            {isActive ? 'Agent is responding' : 'Enter to send · Shift+Enter for newline'}
          </span>
          <div className="flex items-center gap-2">
            {isActive ? (
              <button
                onClick={handleStop}
                disabled={busy}
                className="rounded-lg border border-border px-3.5 py-1.5 text-[13px] font-medium text-text hover:bg-surface-muted disabled:opacity-40"
              >
                Stop
              </button>
            ) : (
              <button
                onClick={() => void handleSubmit()}
                disabled={textareaDisabled || !prompt.trim()}
                className="rounded-lg bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white hover:bg-accent/90 disabled:opacity-40"
              >
                {submitLabel}
              </button>
            )}
          </div>
        </div>
        {helperText && <p className="text-[12px] text-bad">{helperText}</p>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Session detail — transcript body for the selected session
// ---------------------------------------------------------------------------

function ConversationBody({
  dc,
  sessionId,
  onRefetch,
  onRegisterTranscriptRefetch,
  onRegisterSessionRefetch,
  pendingUserText,
  onPendingReconciled,
}: {
  dc: DevcontainerView
  sessionId: string
  onRefetch: () => void
  onRegisterTranscriptRefetch: (fn: () => void) => void
  onRegisterSessionRefetch: (fn: () => void) => void
  pendingUserText: string | null
  onPendingReconciled: () => void
}) {
  const devcontainerId = dc.id
  const { state, refetch } = useApiQuery(
    () => fetchAgentSession(devcontainerId, sessionId),
    [devcontainerId, sessionId],
  )
  const { state: transcriptState, refetch: transcriptRefetch, isFetching: transcriptFetching } = useApiQuery(
    () => fetchAgentSessionTranscript(devcontainerId, sessionId),
    [devcontainerId, sessionId],
  )
  // Per-session pending interventions: fetch inbox events for this session, filtered to
  // blocking + unresolved. Drives the inline card when the session is waiting_for_approval.
  const { state: inboxState, refetch: inboxRefetch } = useApiQuery(
    () => listInboxEvents({ agentSessionId: sessionId }),
    [sessionId],
  )
  const { register } = useSseInvalidation()

  useEffect(() => register('agent_sessions', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', transcriptRefetch), [register, transcriptRefetch])
  useEffect(() => register('inbox', inboxRefetch), [register, inboxRefetch])
  useEffect(() => register('approvals', inboxRefetch), [register, inboxRefetch])

  // Register transcript refetch with parent so ChatComposer can call it post-resume.
  useEffect(() => {
    onRegisterTranscriptRefetch(transcriptRefetch)
  }, [onRegisterTranscriptRefetch, transcriptRefetch])

  useEffect(() => {
    onRegisterSessionRefetch(refetch)
  }, [onRegisterSessionRefetch, refetch])

  // Open the per-session live stream ONLY while the session is active (ADR-0010).
  const isActive = state.kind === 'ready' && ACTIVE_STATUSES.has(state.data.status)
  const transcriptTurns: TranscriptTurn[] = useMemo(
    () =>
      transcriptState.kind === 'ready' && transcriptState.data.state === 'has_turns'
        ? transcriptState.data.turns
        : [],
    [transcriptState],
  )
  const reconciledTurnIds = useMemo(() => new Set(transcriptTurns.map((t) => t.id)), [transcriptTurns])
  const live = useSessionStream(devcontainerId, sessionId, isActive, transcriptRefetch, reconciledTurnIds)
  const runEndBaselineRef = useRef<Set<string> | null>(null)
  const wasEndedRef = useRef(false)
  if (live.ended && !wasEndedRef.current) {
    runEndBaselineRef.current = new Set(transcriptTurns.map((t) => t.id))
  }
  if (!live.ended) runEndBaselineRef.current = null
  wasEndedRef.current = live.ended
  const runEndBaseline = runEndBaselineRef.current
  const streamingTurns = useMemo(
    () => liveOnlyTurns(transcriptTurns, live, transcriptFetching, runEndBaseline),
    [transcriptTurns, live, transcriptFetching, runEndBaseline],
  )
  const mergedTurns = useMemo(
    () => mergeTurns(transcriptTurns, live, transcriptFetching, runEndBaseline),
    [transcriptTurns, live, transcriptFetching, runEndBaseline],
  )

  // Auto-scroll: stick to bottom, pause on user scroll-up, show jump button when unstuck.
  const scrollRef = useRef<HTMLDivElement>(null)
  const [stickToBottom, setStickToBottom] = useState(true)
  // Prevents the onScroll handler from overriding state when we scroll programmatically.
  const programmaticScroll = useRef(false)

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    programmaticScroll.current = true
    try {
      el.scrollTop = el.scrollHeight
    } catch {
      // No-op: read-only scrollTop in test environments (happy-dom with patched metrics).
    }
    Promise.resolve().then(() => { programmaticScroll.current = false })
  }, [])

  function handleScroll() {
    if (programmaticScroll.current) return
    const el = scrollRef.current
    if (!el) return
    setStickToBottom(shouldStick(el.scrollTop, el.scrollHeight, el.clientHeight))
  }

  // Compute merged turns for reconcile counting (user turns land in the transcript only).
  const mergedTurnsForReconcile: TranscriptTurn[] = mergedTurns

  // AC2 reconcile: clear the optimistic bubble only when a NEW matching user turn lands —
  // not when a pre-existing turn with the same text was already in the transcript.
  // Two effects: (1) capture baseline count when pendingText becomes non-empty (at send time,
  // before any new turn lands); (2) clear when live count exceeds that baseline.
  const pendingText = pendingUserText?.trim() ?? ''
  const reconcileBaselineRef = useRef<number | null>(null)

  // Effect 1: capture baseline the moment pendingText transitions null → set.
  useEffect(() => {
    if (!pendingText) {
      reconcileBaselineRef.current = null
      return
    }
    // Only set baseline once per pending — don't overwrite when mergedTurns later changes.
    if (reconcileBaselineRef.current === null) {
      reconcileBaselineRef.current = countMatchingUserTurns(mergedTurnsForReconcile, pendingText)
    }
  // Intentionally omit mergedTurns: baseline must reflect turns AT send time, not later.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingText])

  // Effect 2: clear pending once a new matching turn lands (count exceeds baseline).
  useEffect(() => {
    if (!pendingText || reconcileBaselineRef.current === null) return
    if (countMatchingUserTurns(mergedTurnsForReconcile, pendingText) > reconcileBaselineRef.current) onPendingReconciled()
  }, [mergedTurnsForReconcile, pendingText, onPendingReconciled])

  // Scroll to bottom when new content arrives (turns, live partials, or pending bubble).
  useEffect(() => {
    if (stickToBottom) scrollToBottom()
  }, [transcriptTurns.length, streamingTurns.length, pendingUserText, live.order.length, stickToBottom, scrollToBottom])

  if (state.kind === 'loading' && pendingUserText) {
    return (
      <>
        <div className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-b border-border bg-surface-rail/50 px-4 py-2 text-[11px] text-text-muted">
          <span className="shrink-0 font-mono text-text">{sessionId.slice(0, 8)}</span>
        </div>
        <div className="relative flex-1 overflow-hidden">
          <div ref={scrollRef} data-testid="conversation-scroll" className="h-full overflow-auto px-4 py-4">
            <div className="mx-auto flex max-w-3xl flex-col gap-3">
              <ConversationBubble role="user" sending>
                <p>{pendingUserText}</p>
              </ConversationBubble>
            </div>
          </div>
        </div>
      </>
    )
  }

  if (state.kind === 'loading' && !pendingUserText) {
    return (
      <div className="flex-1 overflow-auto px-4 py-4">
        <p className="text-[13px] text-text-muted">Loading session…</p>
      </div>
    )
  }

  if (state.kind === 'error') {
    if (state.error instanceof ApiError && state.error.code === 'AGENT_SESSION_NOT_FOUND') {
      return (
        <div className="flex-1 overflow-auto px-4 py-4">
          <ErrorState title="Session not found" helper="This session doesn't exist or has been removed." />
        </div>
      )
    }
    return (
      <div className="flex-1 overflow-auto px-4 py-4">
        <ErrorState {...loadError('session')} />
      </div>
    )
  }

  if (state.kind !== 'ready') return null

  const session = state.data
  const showWorking = isWorkingIndicatorVisible(isActive, live)

  // Pending intervention for this session: first blocking + unresolved inbox event.
  // Keyed by event id so the card remounts on intervention change and clears when resolved.
  const pendingIntervention =
    inboxState.kind === 'ready'
      ? (inboxState.data.items.find((e) => isBlocking(e) && e.status !== 'resolved') ?? null)
      : null

  function renderTranscript() {
    if (transcriptState.kind === 'loading' && !pendingUserText && transcriptTurns.length === 0) {
      return <p className="text-[13px] text-text-muted">Loading conversation…</p>
    }

    if (transcriptState.kind === 'error' || (transcriptState.kind === 'ready' && transcriptState.data.state === 'error')) {
      return <ErrorState {...loadError('transcript')} />
    }

    if (transcriptState.kind === 'ready') {
      const transcript = transcriptState.data

      if (transcriptTurns.length > 0 || pendingUserText || streamingTurns.length > 0 || showWorking || pendingIntervention) {
        return (
          <div className="mx-auto flex max-w-3xl flex-col gap-3">
            {transcriptTurns.map((turn) => (
              <ConversationBubble key={turn.id} role={turn.role === 'user' ? 'user' : 'agent'}>
                <BlockContent blocks={turn.blocks} />
              </ConversationBubble>
            ))}
            {pendingUserText && (
              <ConversationBubble role="user" sending>
                <p>{pendingUserText}</p>
              </ConversationBubble>
            )}
            {streamingTurns.map((turn) => (
              <ConversationBubble key={turn.id} role="agent">
                <BlockContent blocks={turn.blocks} />
              </ConversationBubble>
            ))}
            {showWorking && <WorkingIndicator />}
            {pendingIntervention && (
              <InlineInterventionCard
                key={pendingIntervention.id}
                event={pendingIntervention}
                devcontainerId={devcontainerId}
                sessionId={sessionId}
              />
            )}
          </div>
        )
      }

      if (transcript.state === 'summary_fallback') {
        return (
          <div className="space-y-3">
            {transcript.summary_text && (
              <ConversationBubble role="agent">{transcript.summary_text}</ConversationBubble>
            )}
            <p className="text-[13px] text-text-muted">Start the devcontainer to view or continue this conversation.</p>
          </div>
        )
      }

      return <p className="text-[13px] text-text-muted">No conversation yet.</p>
    }

    return null
  }

  void onRefetch // onRefetch triggers session list update after stop; transcript updates via SSE

  return (
    <>
      <div className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-b border-border bg-surface-rail/50 px-4 py-2 text-[11px] text-text-muted">
        <span className="shrink-0 font-mono text-text">{session.id.slice(0, 8)}</span>
        <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium', agentSessionBadgeClass(session.status))}>
          {session.status}
        </span>
        {session.prompt && <span className="min-w-0 flex-1 truncate text-text">· {session.prompt}</span>}
      </div>
      <div className="relative flex-1 overflow-hidden">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          data-testid="conversation-scroll"
          className="h-full overflow-auto px-4 py-4"
        >
          {renderTranscript()}
        </div>
        {!stickToBottom && (
          <button
            onClick={() => { scrollToBottom(); setStickToBottom(true) }}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-accent px-3 py-1 text-[12px] font-medium text-white shadow-md"
          >
            Jump to latest
          </button>
        )}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Left pane — devcontainer info + agent sessions list
// ---------------------------------------------------------------------------

function AgentSessionsList({
  dc,
  sessions,
  selectedId,
  onSelect,
  onSessionsChange,
}: {
  dc: DevcontainerView
  sessions: AgentSession[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  onSessionsChange: () => void
}) {
  const devcontainerId = dc.id
  const [deletingId, setDeletingId] = useState<string | null>(null)

  async function handleDelete(sessionId: string) {
    setDeletingId(sessionId)
    try {
      await deleteAgentSession(devcontainerId, sessionId)
      if (selectedId === sessionId) onSelect(null)
      onSessionsChange()
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="p-3">
      <h3 className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Sessions</h3>
      {sessions.length === 0 ? (
        <p className="px-1 text-[13px] text-text-muted">No chats yet — start one below.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-bg">
          {[...sessions].reverse().map((s) => (
            <SessionRow
              key={s.id}
              session={s}
              selected={s.id === selectedId}
              onSelect={(id) => onSelect(selectedId === id ? null : id)}
              onDelete={handleDelete}
              deleting={deletingId === s.id}
            />
          ))}
        </div>
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

// ---------------------------------------------------------------------------
// Two-pane layout inside the loaded devcontainer
// ---------------------------------------------------------------------------

function TwoPaneLayout({
  dc,
  sessions,
  refetchSessions,
}: {
  dc: DevcontainerView
  sessions: AgentSession[]
  refetchSessions: () => void
}) {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [sessionsCollapsed, setSessionsCollapsed] = useState(false)
  const sessionRefetchRef = useRef<() => void>(() => {})
  const [pendingUserText, setPendingUserText] = useState<string | null>(null)

  // Follow the active session automatically; keeps streaming connected after Start.
  useEffect(() => {
    const active = sessions.find((s) => ACTIVE_STATUSES.has(s.status))
    if (active) setSelectedSessionId((prev) => prev ?? active.id)
  }, [sessions])

  const composerMode = resolveComposerMode(dc, sessions, selectedSessionId)
  const activeSession = sessions.find((s) => ACTIVE_STATUSES.has(s.status)) ?? null
  const conversationSessionId = selectedSessionId ?? activeSession?.id ?? null

  function handleComposerAction(sessionId?: string) {
    if (sessionId) setSelectedSessionId(sessionId)
    refetchSessions()
    sessionRefetchRef.current()
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <DevcontainerInfo dc={dc} />

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {!sessionsCollapsed && (
          <div className="flex w-[260px] shrink-0 flex-col overflow-hidden border-r border-border bg-surface-rail">
            <div className="min-h-0 flex-1 overflow-auto">
              <AgentSessionsList
              dc={dc}
              sessions={sessions}
              selectedId={conversationSessionId}
              onSelect={setSelectedSessionId}
              onSessionsChange={refetchSessions}
            />
            </div>
          </div>
        )}

        <button
          onClick={() => setSessionsCollapsed((v) => !v)}
          title={sessionsCollapsed ? 'Expand sessions' : 'Collapse sessions'}
          className="flex w-5 shrink-0 items-center justify-center border-r border-border bg-surface-rail text-text-muted hover:bg-surface-muted"
        >
          {sessionsCollapsed ? chevronRightIcon : chevronLeftIcon}
        </button>

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-bg">
          {conversationSessionId ? (
            <ConversationBody
              key={conversationSessionId}
              dc={dc}
              sessionId={conversationSessionId}
              onRefetch={refetchSessions}
              onRegisterTranscriptRefetch={() => {}}
              onRegisterSessionRefetch={(fn) => { sessionRefetchRef.current = fn }}
              pendingUserText={pendingUserText}
              onPendingReconciled={() => setPendingUserText(null)}
            />
          ) : (
            <div className="flex flex-1 flex-col overflow-hidden">
              {pendingUserText ? (
                <div className="flex-1 overflow-auto px-4 py-4">
                  <div className="mx-auto max-w-3xl">
                    <ConversationBubble role="user" sending>
                      <p>{pendingUserText}</p>
                    </ConversationBubble>
                  </div>
                </div>
              ) : (
                <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-8 text-center">
                  <p className="text-[15px] font-medium text-text">Start a conversation</p>
                  <p className="max-w-sm text-[13px] text-text-muted">
                    Type a message below to run the agent in this devcontainer.
                  </p>
                </div>
              )}
            </div>
          )}
          <ChatComposer
            dc={dc}
            mode={composerMode}
            onAction={handleComposerAction}
            onOptimisticSend={(t) => setPendingUserText(t)}
          />
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page root
// ---------------------------------------------------------------------------

export function DevcontainerDetail() {
  const { id } = useParams<{ id: string }>()
  const { register } = useSseInvalidation()

  const { state, refetch } = useApiQuery(() => fetchDevcontainer(id!), [id])
  const { state: sessionsState, refetch: refetchSessions } = useApiQuery(
    () => fetchAgentSessions(id!),
    [id],
  )

  useEffect(() => register('devcontainers', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetchSessions), [register, refetchSessions])

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0">
        <PageHeader title="Devcontainer" crumbs="Detail" />
      </div>
      <QueryBoundary state={state} error={errorElement(state.kind === 'error' ? state.error : null)}>
        {(dc) => (
          sessionsState.kind === 'ready' ? (
            <TwoPaneLayout dc={dc} sessions={sessionsState.data.items} refetchSessions={refetchSessions} />
          ) : sessionsState.kind === 'loading' ? (
            <div className="flex flex-1 items-center justify-center">
              <p className="text-[13px] text-text-muted">Loading…</p>
            </div>
          ) : null
        )}
      </QueryBoundary>
    </div>
  )
}
