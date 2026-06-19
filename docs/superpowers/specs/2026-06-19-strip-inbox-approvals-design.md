# Strip Inbox, Approvals & Interventions — Refocus on Devcontainer Detail

**Date:** 2026-06-19
**Status:** Approved (revised after rebasing onto current `refactor-runtimes`)

## Problem

The tool was over-scoped early. Inbox, Approvals, and the inline User-Intervention
flow are not required for the tool to be usable. The core value is the
**devcontainer detail page** (now a two-pane chat with a live Session Stream).
Remove the rest so the surface area is small and focused.

## Revision note

The original spec targeted an older snapshot. `refactor-runtimes` has since
advanced 12 commits (VIB-108…113) adding a two-pane chat + live Session Stream,
and **VIB-113 wove "inline User Interventions" into that chat** via the
`lib/intervention` module. The work is being **redone fresh** on the current code,
and the scope now **also removes interventions** (the user runs agents inside the
devcontainer with full permissions — no approval/intervention gate is needed).

## Scope

- **Frontend + mock only.** The backend is intentionally left to break; separate
  follow-up. No backend/CLI changes.
- Remove **all** of: Inbox, Approvals (standalone page **and** the inline
  `waiting_for_approval` flow), and the entire `lib/intervention` module
  **including** its inline use inside the chat (VIB-113).
- **The chat / Session Stream must keep working.** Removal is surgical inside
  `DevcontainerDetail.tsx`; `lib/chat/*`, `lib/stream/*`, and
  `mock/agentSessionStreams.ts` are untouched.
- Devcontainer detail page: **clean up only** — no redesign.

## Key facts established by exploration

- `lib/intervention` is imported by exactly three files: `routes/Inbox.tsx`,
  `routes/Approvals.tsx` (both deleted), and `routes/DevcontainerDetail.tsx`
  (`InlineInterventionCard`, surgical edit).
- The endpoints `sendAgentSessionUserInput`, `resolveAgentSessionApproval`,
  `listInboxEvents`, `fetchInboxEvent`, `markInboxEventRead`, `resolveInboxEvent`,
  `listApprovalRequests`, `fetchApprovalRequest` are used **only** by the removed
  features (verified: no surviving chat code depends on them) → all safe to delete.
- No surviving chat endpoint (`startAgentSession`, `resumeAgentSession`,
  `stopAgentSession`, `fetchAgentSessionTranscript`, `openAgentSessionStream`, …)
  touches interventions.

## Removal Inventory

### Files to delete
- Routes: `routes/Inbox.tsx`, `routes/Approvals.tsx`, `routes/inboxViews.ts`
- Route tests: `routes/__tests__/Inbox.test.tsx`, `Approvals.test.tsx`,
  `inboxViews.test.ts`
- Mock state: `mock/state/inbox.ts`, `mock/state/approvals.ts`
- Mock state tests: `mock/state/__tests__/inbox.test.ts`, `approvals.test.ts`
- Mock handler tests: `mock/__tests__/inbox.test.ts`, `mock/__tests__/approvals.test.ts`
- Whole module: `lib/intervention/` (`ActionButton.tsx`, `InlineInterventionCard.tsx`,
  `StatusNote.tsx`, `useInterventionAction.ts`, `index.ts`,
  `__tests__/useInterventionAction.test.ts`)

### Surgical edits — surviving code
- `routes/DevcontainerDetail.tsx`: remove the `InlineInterventionCard` import, the
  `isBlocking`/`inboxViews` import, the `listInboxEvents` import + its `useApiQuery`
  hook, the two `register('inbox'|'approvals', …)` effects, the `pendingIntervention`
  computation, the `|| pendingIntervention` render condition, and the
  `<InlineInterventionCard>` element. Drop `waiting_for_approval` from
  `ACTIVE_STATUSES` and the `agentSessionBadgeClass` switch.
- `routes/router.tsx`: drop the `inbox` and `approvals` routes + imports.
- `components/Sidebar.tsx`: drop Inbox + Approvals nav items → Devcontainers + Settings.
- `lib/api/endpoints.ts` + `types.ts`: remove the 8 endpoint functions above and all
  backing DTOs (`InboxEvent*`, `ApprovalRequest*`, `ApprovalStatus`,
  `ApprovalResolution`, `AgentSessionApprovalBody`, `AgentSessionUserInputBody`),
  and drop `'waiting_for_approval'` from `AgentSessionStatus`.
- `lib/events/types.ts`: `Scope` → `'devcontainers' | 'agent_sessions' | 'runtime'`.
- `mock/handlers.ts`: remove inbox/approval/user-input/approval-resolution handlers +
  imports + any now-dead helper.
- `mock/fixtures.ts`: remove `inboxEvents`/`approvalRequests` + their type imports.
- `mock/state/seeds.ts`: `as-seed-0001` status → `'running'`; drop inbox/approval
  mentions from comments.
- `mock/state/agentSessions.ts`: `ACTIVE_STATUSES` → `['starting','running']`.
- `mock/RailMock.tsx`, `routes/MockScenarios.tsx`: trim `SCOPES` (+ `SCOPE_DESC`).

### Cross-cutting test prunes
`routes/__tests__/DevcontainerDetail.test.tsx` (remove intervention AC tests,
the `waiting_for_approval` badge test, and the inbox/approval endpoint mocks),
`lib/events/__tests__/coordinator.test.ts`, `SseProvider.test.tsx`,
`mock/__tests__/handlers.test.ts`, `events.test.ts`, `mockSseRefetch.test.tsx`,
`scenario.test.ts`.

### Docs
`apps/web/CLAUDE.md`, `apps/web/src/mock/README.md`.

## Decisions

- **`waiting_for_approval` removed from the frontend status union** even though the
  backend enum still emits it (backend out of scope). A stray value falls through to
  the default muted badge — harmless.

## Success Criteria

- `pnpm build` (tsc + vite) green; `pnpm test` green.
- Sidebar shows only Devcontainers + Settings.
- **Chat / Session Stream still fully functional** (two-pane layout, live transcript,
  composer, streaming deltas, SSE invalidation) — only the intervention card is gone.
- Zero `inbox` / `approval` / `waiting_for_approval` / `intervention` references in
  `apps/web/src` (and the two docs).

## Out of Scope

- Backend cleanup (follow-up).
- Devcontainer detail page redesign / new features.
- `lib/chat`, `lib/stream`, `mock/agentSessionStreams.ts` — must remain untouched.
