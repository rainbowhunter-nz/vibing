import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import {
  listInboxEvents,
  fetchInboxEvent,
  markInboxEventRead,
  resolveInboxEvent,
  sendAgentSessionUserInput,
  resolveAgentSessionApproval,
  useApiQuery,
  ApiError,
  type InboxEvent,
  type InboxEventDetail,
  type QueryState,
} from '../lib/api'
import { useInterventionAction, ActionButton, StatusNote } from '../lib/intervention'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { formatRelativeTime } from '../lib/time'
import { cn } from '../lib/cn'
import { needsAttentionEvents, allEvents, isBlocking } from './inboxViews'

const inboxIcon = (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
  </svg>
)

type View = 'needs' | 'all'

const TYPE_LABEL: Record<InboxEvent['event_type'], string> = {
  question: 'question',
  approval_request: 'approval request',
  completion: 'completion',
  failure: 'failure',
}

function typeBadgeClass(type: InboxEvent['event_type']): string {
  switch (type) {
    case 'question':
      return 'bg-accent-bg text-accent'
    case 'approval_request':
      return 'bg-amber-100 text-amber-800'
    case 'failure':
      return 'bg-red-100 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function ViewTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-md px-2.5 py-1 text-xs font-semibold',
        active ? 'bg-accent-bg text-accent' : 'text-text-muted hover:bg-surface-muted',
      )}
    >
      {label}
    </button>
  )
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-surface-muted px-4 py-1.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
      {children}
    </div>
  )
}

function InboxRow({
  event,
  selected,
  onSelect,
}: {
  event: InboxEvent
  selected: boolean
  onSelect: (id: string) => void
}) {
  return (
    <button
      onClick={() => onSelect(event.id)}
      className={cn(
        'flex w-full flex-col gap-1 border-b border-border px-4 py-2.5 text-left',
        selected ? 'border-l-[3px] border-l-accent bg-accent-bg/40 pl-[13px]' : 'hover:bg-surface-muted',
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium capitalize', typeBadgeClass(event.event_type))}>
          {TYPE_LABEL[event.event_type]}
        </span>
        <span className="text-[12.5px] font-semibold text-text">{event.devcontainer_id}</span>
      </div>
      <div className="text-[11px] text-text-muted">
        <span>{event.status}</span> · {formatRelativeTime(event.created_at)}
      </div>
    </button>
  )
}

function InboxList({
  events,
  view,
  selectedId,
  onSelect,
}: {
  events: InboxEvent[]
  view: View
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const row = (e: InboxEvent) => (
    <InboxRow key={e.id} event={e} selected={e.id === selectedId} onSelect={onSelect} />
  )

  if (view === 'all') return <div>{events.map(row)}</div>

  const blocking = events.filter(isBlocking)
  const failures = events.filter((e) => e.event_type === 'failure')
  return (
    <div>
      {blocking.length > 0 && (
        <>
          <GroupLabel>Blocking</GroupLabel>
          {blocking.map(row)}
        </>
      )}
      {failures.length > 0 && (
        <>
          <GroupLabel>Failures</GroupLabel>
          {failures.map(row)}
        </>
      )}
    </div>
  )
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 border-b border-border px-4 py-3 last:border-b-0">
      <span className="w-32 shrink-0 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">{label}</span>
      <span className="text-[13px] text-text">{children}</span>
    </div>
  )
}

function ApprovalControls({ detail }: { detail: InboxEventDetail }) {
  const { state, run } = useInterventionAction('APPROVAL_REQUEST_NOT_PENDING')
  const submitting = state.kind === 'submitting'
  const resolved = detail.status === 'resolved'
  const showActions = !resolved && state.kind !== 'awaiting' && state.kind !== 'stale'

  const resolve = (resolution: 'approved' | 'rejected') =>
    run(resolution, () =>
      resolveAgentSessionApproval(detail.devcontainer_id, detail.agent_session_id ?? '', {
        approval_request_id: detail.approval_request_id ?? '',
        resolution,
      }),
    )

  return (
    <div className="px-4 pb-4">
      {showActions && (
        <div className="flex justify-end gap-2">
          <ActionButton
            label={submitting && state.tag === 'rejected' ? 'Rejecting…' : 'Reject'}
            onClick={() => resolve('rejected')}
            disabled={submitting}
            variant="reject"
          />
          <ActionButton
            label={submitting && state.tag === 'approved' ? 'Approving…' : 'Approve'}
            onClick={() => resolve('approved')}
            disabled={submitting}
            variant="approve"
          />
        </div>
      )}
      <StatusNote
        state={state}
        awaitingNote="✓ Submitted · awaiting runtime…"
        staleNote="Already resolved elsewhere — no longer pending."
      />
    </div>
  )
}

function AnswerControls({ detail }: { detail: InboxEventDetail }) {
  const { state, run } = useInterventionAction('INBOX_EVENT_NOT_ACTIONABLE')
  const [text, setText] = useState('')
  const submitting = state.kind === 'submitting'
  const resolved = detail.status === 'resolved'
  const showForm = !resolved && state.kind !== 'awaiting' && state.kind !== 'stale'

  const send = () =>
    run('answer', () =>
      sendAgentSessionUserInput(detail.devcontainer_id, detail.agent_session_id ?? '', {
        inbox_event_id: detail.id,
        text,
      }),
    )

  return (
    <div className="flex flex-col gap-2 px-4 pb-4">
      {showForm && (
        <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={submitting}
            placeholder="Type your answer…"
            className="min-h-[64px] rounded-md border border-border px-3 py-2 text-[12.5px] disabled:opacity-40"
          />
          <div className="flex justify-end">
            <button
              onClick={send}
              disabled={submitting || text.trim() === ''}
              className="rounded-md bg-accent px-3 py-1 text-[12px] font-semibold text-white disabled:opacity-40"
            >
              {submitting ? 'Sending…' : 'Send answer'}
            </button>
          </div>
        </>
      )}
      <StatusNote
        state={state}
        awaitingNote="✓ Answer sent · awaiting runtime…"
        staleNote="This question is no longer awaiting an answer."
      />
    </div>
  )
}

function MetaLine({ detail }: { detail: InboxEventDetail }) {
  const session = detail.agent_session ? ` · session ${detail.agent_session.id.slice(0, 8)}` : ''
  return (
    <div className="mb-2 px-4 text-[11px] text-text-muted">
      {detail.devcontainer.name}
      {session} · {formatRelativeTime(detail.created_at)}
    </div>
  )
}

function Bubble({ children }: { children: React.ReactNode }) {
  return <div className="mx-4 rounded-[10px] bg-surface-muted px-3 py-2.5 text-[13px] leading-relaxed text-text">{children}</div>
}

function InboxDetail({
  detail,
  onClose,
  onResolve,
  resolving,
}: {
  detail: InboxEventDetail
  onClose: () => void
  onResolve: () => void
  resolving: boolean
}) {
  return (
    <div className="pt-4">
      <div className="mb-3 flex items-center justify-between px-4">
        <h2 className="text-base font-semibold capitalize text-text">
          <span className={cn('mr-2 rounded-full px-2 py-0.5 text-[11px] font-medium', typeBadgeClass(detail.event_type))}>
            {TYPE_LABEL[detail.event_type]}
          </span>
        </h2>
        <button
          onClick={onClose}
          title="Close"
          className="flex h-7 w-7 items-center justify-center rounded-[5px] text-text-muted hover:bg-surface-muted"
        >
          ✕
        </button>
      </div>
      <MetaLine detail={detail} />
      <div className="mb-2 flex justify-end px-4">
        {detail.status === 'resolved' ? (
          <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">Resolved</span>
        ) : (
          <ActionButton
            label={resolving ? 'Resolving…' : 'Resolve'}
            onClick={onResolve}
            disabled={resolving}
            variant="reject"
          />
        )}
      </div>

      {detail.event_type === 'question' && (
        <>
          <Bubble>{detail.content ?? 'The agent asked a question.'}</Bubble>
          <div className="h-3" />
          <AnswerControls detail={detail} />
        </>
      )}

      {detail.event_type === 'approval_request' && (
        <>
          <Bubble>
            {detail.approval_request
              ? `Claude wants to ${detail.approval_request.requested_action}`
              : 'Approval requested.'}
          </Bubble>
          <div className="h-3" />
          <ApprovalControls detail={detail} />
        </>
      )}

      {(detail.event_type === 'completion' || detail.event_type === 'failure') && (
        <>
          {detail.content && (
            <>
              <Bubble>{detail.content}</Bubble>
              <div className="h-3" />
            </>
          )}
          <div className="mx-4 rounded-md border border-border">
            <DetailRow label="Status">{detail.status}</DetailRow>
            <DetailRow label="Devcontainer">{detail.devcontainer.name}</DetailRow>
            <DetailRow label="Agent session">
              {detail.agent_session ? `${detail.agent_session.id.slice(0, 8)} · ${detail.agent_session.status}` : '—'}
            </DetailRow>
            <DetailRow label="Created">{formatRelativeTime(detail.created_at)}</DetailRow>
          </div>
        </>
      )}
    </div>
  )
}

function detailErrorElement(state: QueryState<InboxEventDetail>) {
  if (state.kind === 'error' && state.error instanceof ApiError && state.error.code === 'INBOX_EVENT_NOT_FOUND') {
    return <ErrorState title="Inbox event not found" helper="This item doesn't exist or has been removed." />
  }
  return <ErrorState {...loadError('inbox event')} />
}

function InboxDetailPanel({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { state, refetch } = useApiQuery(() => fetchInboxEvent(id), [id])
  const { register } = useSseInvalidation()
  const markedRead = useRef(false)
  const [resolving, setResolving] = useState(false)

  useEffect(() => register('inbox', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetch), [register, refetch])
  useEffect(() => register('approvals', refetch), [register, refetch])

  useEffect(() => {
    // Fire once per opened event; the panel is keyed by id so the ref resets on selection change.
    if (state.kind === 'ready' && state.data.status === 'unread' && !markedRead.current) {
      markedRead.current = true
      markInboxEventRead(state.data.id)
        .then(() => {
          refetch()
          onChanged()
        })
        .catch(() => {
          markedRead.current = false // allow retry on next state change
        })
    }
  }, [state, refetch, onChanged])

  const resolve = () => {
    setResolving(true)
    resolveInboxEvent(id)
      .then(() => {
        refetch()
        onChanged()
      })
      .catch(() => {}) // button re-enables via finally; user can retry
      .finally(() => setResolving(false))
  }

  return (
    <QueryBoundary state={state} error={detailErrorElement(state)}>
      {(detail) => (
        <InboxDetail detail={detail} onClose={onClose} onResolve={resolve} resolving={resolving} />
      )}
    </QueryBoundary>
  )
}

export function Inbox() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('selected')
  const [view, setView] = useState<View>('needs')
  const { state, refetch } = useApiQuery(() => listInboxEvents(), [])
  const { register } = useSseInvalidation()

  useEffect(() => register('inbox', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetch), [register, refetch])
  useEffect(() => register('approvals', refetch), [register, refetch])

  function select(id: string) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('selected', id)
        return next
      },
      { replace: false },
    )
  }

  function clearSelection() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('selected')
      return next
    })
  }

  const crumbs = state.kind === 'ready' ? `${needsAttentionEvents(state.data.items).length} need attention` : undefined

  return (
    <>
      <PageHeader title="Inbox" crumbs={crumbs} />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-[340px] shrink-0 flex-col border-r border-border">
          <div className="flex gap-1.5 border-b border-border px-4 py-2.5">
            <ViewTab label="Needs Attention" active={view === 'needs'} onClick={() => setView('needs')} />
            <ViewTab label="All" active={view === 'all'} onClick={() => setView('all')} />
          </div>
          <div className="flex-1 overflow-auto">
            <QueryBoundary state={state} error={<ErrorState {...loadError('inbox')} />}>
              {(data) => {
                const events = view === 'needs' ? needsAttentionEvents(data.items) : allEvents(data.items)
                return events.length === 0 ? (
                  <EmptyState
                    icon={inboxIcon}
                    title={view === 'needs' ? 'Nothing needs attention' : 'Inbox is empty'}
                    helper="Questions, approval requests, failures and completions from your agent sessions appear here."
                  />
                ) : (
                  <InboxList events={events} view={view} selectedId={selectedId} onSelect={select} />
                )
              }}
            </QueryBoundary>
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          {selectedId ? (
            <InboxDetailPanel key={selectedId} id={selectedId} onClose={clearSelection} onChanged={refetch} />
          ) : (
            <EmptyState icon={inboxIcon} title="Select an item" helper="Choose an Inbox event to see its details." />
          )}
        </div>
      </div>
    </>
  )
}
