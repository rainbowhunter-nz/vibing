import { useState } from 'react'
import type { InboxEvent } from '../api/types'
import { resolveAgentSessionApproval, sendAgentSessionUserInput } from '../api/endpoints'
import { useInterventionAction } from './useInterventionAction'
import { ActionButton } from './ActionButton'
import { StatusNote } from './StatusNote'

/**
 * Inline card rendered in the chat flow when the selected session is waiting on a human.
 *
 * NOTE: This card is currently MOCK-ONLY. The agent runs with bypassPermissions and does not
 * yet emit approval_requested / agent_asked_question events. Inline rendering will activate
 * once the --permission-prompt-tool work (future VIB ticket) wires up those runtime events.
 * The card drives the EXISTING intervention endpoints — no action logic is duplicated here.
 */
export function InlineInterventionCard({
  event,
  devcontainerId,
  sessionId,
}: {
  event: InboxEvent
  devcontainerId: string
  sessionId: string
}) {
  return (
    <div className="my-2 rounded-[10px] border border-accent/30 bg-accent-bg/20 px-4 py-3">
      {event.event_type === 'approval_request' ? (
        <ApprovalCard event={event} devcontainerId={devcontainerId} sessionId={sessionId} />
      ) : (
        <QuestionCard event={event} devcontainerId={devcontainerId} sessionId={sessionId} />
      )}
    </div>
  )
}

function ApprovalCard({
  event,
  devcontainerId,
  sessionId,
}: {
  event: InboxEvent
  devcontainerId: string
  sessionId: string
}) {
  const { state, run } = useInterventionAction('APPROVAL_REQUEST_NOT_PENDING')
  const submitting = state.kind === 'submitting'
  const showActions = state.kind !== 'awaiting' && state.kind !== 'stale'

  const resolve = (resolution: 'approved' | 'rejected') =>
    run(resolution, () =>
      resolveAgentSessionApproval(devcontainerId, sessionId, {
        approval_request_id: event.approval_request_id ?? '',
        resolution,
      }),
    )

  return (
    <div>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.05em] text-accent">
        Approval Request
      </div>
      {showActions && (
        <div className="flex gap-2">
          <ActionButton
            label={submitting && state.tag === 'approved' ? 'Approving…' : 'Approve'}
            onClick={() => resolve('approved')}
            disabled={submitting}
            variant="approve"
          />
          <ActionButton
            label={submitting && state.tag === 'rejected' ? 'Rejecting…' : 'Reject'}
            onClick={() => resolve('rejected')}
            disabled={submitting}
            variant="reject"
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

function QuestionCard({
  event,
  devcontainerId,
  sessionId,
}: {
  event: InboxEvent
  devcontainerId: string
  sessionId: string
}) {
  const { state, run } = useInterventionAction('INBOX_EVENT_NOT_ACTIONABLE')
  const [text, setText] = useState('')
  const submitting = state.kind === 'submitting'
  const showForm = state.kind !== 'awaiting' && state.kind !== 'stale'

  const send = () =>
    run('answer', () =>
      sendAgentSessionUserInput(devcontainerId, sessionId, {
        inbox_event_id: event.id,
        text,
      }),
    )

  return (
    <div>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.05em] text-accent">
        Question
      </div>
      {showForm && (
        <div className="flex flex-col gap-2">
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
        </div>
      )}
      <StatusNote
        state={state}
        awaitingNote="✓ Answer sent · awaiting runtime…"
        staleNote="This question is no longer awaiting an answer."
      />
    </div>
  )
}
