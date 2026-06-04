# VIB-50 — Inbox User Intervention actions

**Date:** 2026-06-04
**Epic:** VIB-37 (Frontend Inbox and Approvals Workflows)
**Blocked by:** VIB-40, VIB-41, VIB-47 (all Done)

## Goal

Add action controls to the Inbox detail panel so users can answer questions and
approve/reject Approval Requests directly from triage. UI feels immediate: local
sending state → accepted/pending on `202` → resolved via SSE-triggered refetch.

## Decisions

- **Reuse:** extract the action state machine (currently inline in `Approvals.tsx`)
  into a shared intervention module; refactor `Approvals.tsx` to consume it. No
  duplication.
- **Question content:** include it. The `AGENT_ASKED_QUESTION` payload is currently
  discarded; persist it so the panel shows what was asked. Requires backend changes.
- **Layout:** conversational/chat style — content as a bubble, controls as the reply
  area. Replaces the metadata table for question/approval events; completion/failure
  keep the existing read-only rows.

## Backend — expose question content

A question Inbox Event has no displayable body today. The reducer maps
`AGENT_ASKED_QUESTION → QUESTION` but drops the payload. The runtime does not yet
emit this event in real code, so we define the payload convention now.

1. **Schema** (`core/schema.py`): add nullable `content TEXT` to the `inbox_events`
   `CREATE TABLE`; bump `SCHEMA_VERSION` `"2" → "3"`.
   - No migration runner exists (`apply_schema` is `CREATE TABLE IF NOT EXISTS`).
     Existing dev DBs do **not** auto-migrate — recreate by deleting the sqlite file.
     Accepted for this MVP.
2. **Reducer** (`core/reducer.py`): payload convention `payload["question"]`. Add
   `inbox_content: str | None` to `ProjectionUpdates`, set it only in the
   `AGENT_ASKED_QUESTION` branch, thread it into `inbox.create(...)`.
3. **Repository** (`repositories/inbox.py`): add `content` to the dataclass,
   `_COLUMNS`, `create()` signature, INSERT, and `_row_to_inbox` mapping.
4. **API schema** (`api/schemas/inbox.py`): add `content: str | None` to
   `InboxEventDetail` only. List rows don't need it; it flows through the detail
   endpoint's existing `**vars(event)`.
5. **Sample data** (`dev/sample_data.py`): give the sample question event `content`.

## Frontend — shared intervention module

New `src/lib/intervention/`:

- **`useInterventionAction({ submit, staleCode })`** — owns the
  `idle | submitting | awaiting | stale | error` machine. Calls `submit`, maps a
  `staleCode` 409 to `stale`, other failures to `error`, success (`202`) to `awaiting`.
- **`ActionButtons`** — approve/reject, disabled while submitting, progress labels
  ("Approving…" / "Rejecting…").
- **`AnswerComposer`** — textarea + send, disabled while submitting.
- Shared note rendering for awaiting / stale / error.

**Refactor** `Approvals.tsx` `ApprovalRow` to consume `useInterventionAction` +
`ActionButtons` — single source of truth.

## Inbox detail panel (conversational)

Rewrite `InboxDetail` (`routes/Inbox.tsx`):

- Header (type badge + title + close), compact meta line
  (`devcontainer · session 3f9c… · 2m ago`), content **bubble**.
- **Question** → bubble = `content`; `AnswerComposer` calls
  `sendAgentSessionUserInput(devcontainer_id, agent_session_id, { inbox_event_id, text })`;
  stale code `INBOX_EVENT_NOT_ACTIONABLE`.
- **Approval** → bubble = `requested_action`; `ActionButtons` call
  `resolveAgentSessionApproval(devcontainer_id, agent_session_id, { approval_request_id, resolution })`;
  stale code `APPROVAL_REQUEST_NOT_PENDING`.
- **Completion / failure** → keep today's read-only metadata rows, no controls.
- Controls disabled while in flight. `202` → awaiting note. Existing SSE registrations
  (`inbox`, `approvals`, `agent_sessions`) drive the resolved-state refetch.
- TS type (`lib/api/types.ts`): add `content?: string | null` to `InboxEventDetail`.

### State treatments (approved)

| State | Controls | Note |
|-------|----------|------|
| idle | shown | — |
| submitting | disabled | button label "Approving…" / "Sending…" |
| awaiting (202) | hidden | "✓ Submitted · awaiting runtime…" (approval, generic so it fits approve+reject) / "✓ Answer sent · awaiting runtime…" (question) |
| stale (409) | hidden | "Already resolved elsewhere — no longer pending." (question: "no longer awaiting an answer.") |
| error | shown | "Couldn't submit — try again." |

## Testing

- **Inbox route tests** (`routes/__tests__/Inbox.test.tsx`): answer submit, approve,
  reject, in-flight disabled, accepted-after-202, resolved-after-invalidation
  (mock `EventSource`), stale-error for both 409 codes.
- **Approvals tests**: stay green through the refactor.
- **Backend tests** (`tests/api`): reducer captures `payload["question"]` into content;
  repo stores/returns `content`; inbox detail endpoint includes `content`.

## Out of scope

- Runtime emitting real `AGENT_ASKED_QUESTION` events (only the payload convention is
  defined here).
- A general migration framework — schema change rides the existing recreate-on-dev model.
