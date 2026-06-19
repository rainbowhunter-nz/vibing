# Strip Inbox, Approvals & Interventions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Remove Inbox, Approvals (standalone + inline `waiting_for_approval`), and the entire `lib/intervention` module (including its inline use in the chat) from the frontend + mock layer, leaving Devcontainers + Settings — without breaking the two-pane chat / Session Stream.

**Architecture:** Pure deletion/cleanup against the CURRENT `refactor-runtimes` code (post VIB-108…113 chat rework). NOT TDD. Each task removes a cohesive slice, verified by the existing vitest suite, then committed. Ordering removes *consumers before producers* so the suite stays green per commit. `DevcontainerDetail.tsx` is a SURVIVING file edited surgically — never deleted. `lib/chat/*`, `lib/stream/*`, `mock/agentSessionStreams.ts` are OUT OF SCOPE — do not touch. Final task runs full `pnpm build` (tsc + vite). Backend (Python `src/`) intentionally left broken.

**Tech Stack:** React + Vite + TypeScript + Tailwind, vitest, MSW.

**All commands run from `apps/web/`.** Spec: `docs/superpowers/specs/2026-06-19-strip-inbox-approvals-design.md`.

**Critical ordering note:** `DevcontainerDetail.tsx` currently imports `isBlocking` from `./inboxViews`, `InlineInterventionCard` from `../lib/intervention`, and `listInboxEvents`. So Task 1 MUST surgically clean `DevcontainerDetail.tsx` BEFORE Task 2 deletes `inboxViews.ts` and Task 3 deletes `lib/intervention/`.

---

### Task 1: Remove intervention/inbox seams from DevcontainerDetail (surgical)

**Files:**
- Modify: `apps/web/src/routes/DevcontainerDetail.tsx`
- Modify: `apps/web/src/routes/__tests__/DevcontainerDetail.test.tsx`

- [ ] **Step 1: Fix the imports (lines 6, 14, 15)**

Line 6 — remove `listInboxEvents` from the `'../lib/api'` import. It becomes:
```tsx
import { fetchDevcontainer, fetchAgentSessions, fetchAgentSession, fetchAgentSessionTranscript, startAgentSession, stopAgentSession, resumeAgentSession, deleteAgentSession, useApiQuery, ApiError } from '../lib/api'
```
Delete line 14 entirely: `import { InlineInterventionCard } from '../lib/intervention'`
Delete line 15 entirely: `import { isBlocking } from './inboxViews'`

- [ ] **Step 2: Trim status sets/badges**

Line 17 → `const ACTIVE_STATUSES = new Set<string>(['starting', 'running'])`

In `agentSessionBadgeClass` (lines 56-68), remove the `case 'waiting_for_approval':` line so `'starting'` is the lone accent case:
```tsx
function agentSessionBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-emerald-100 text-emerald-800'
    case 'starting':
      return 'bg-accent-bg text-accent'
    case 'failed':
      return 'bg-red-100 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}
```

- [ ] **Step 3: Remove the inbox fetch hook and its SSE registrations (lines 421-432)**

Delete the `inboxState`/`inboxRefetch` block (the comment + `useApiQuery` call, lines 421-426):
```tsx
  // Per-session pending interventions: fetch inbox events for this session, filtered to
  // blocking + unresolved. Drives the inline card when the session is waiting_for_approval.
  const { state: inboxState, refetch: inboxRefetch } = useApiQuery(
    () => listInboxEvents({ agentSessionId: sessionId }),
    [sessionId],
  )
```
And delete the two registration effects (lines 431-432):
```tsx
  useEffect(() => register('inbox', inboxRefetch), [register, inboxRefetch])
  useEffect(() => register('approvals', inboxRefetch), [register, inboxRefetch])
```
Keep the two `register('agent_sessions', …)` effects above them.

- [ ] **Step 4: Remove pendingIntervention + the card render (lines 572-609)**

Delete the `pendingIntervention` computation (lines 572-577):
```tsx
  // Pending intervention for this session: first blocking + unresolved inbox event.
  // Keyed by event id so the card remounts on intervention change and clears when resolved.
  const pendingIntervention =
    inboxState.kind === 'ready'
      ? (inboxState.data.items.find((e) => isBlocking(e) && e.status !== 'resolved') ?? null)
      : null
```
In `renderTranscript`, change the condition on line 583 to drop `|| pendingIntervention`:
```tsx
    if (transcriptTurns.length > 0 || pendingUserText || streamingTurns.length > 0 || showWorking) {
```
And delete the rendered card (lines 602-609):
```tsx
          {pendingIntervention && (
            <InlineInterventionCard
              key={pendingIntervention.id}
              event={pendingIntervention}
              devcontainerId={devcontainerId}
              sessionId={sessionId}
            />
          )}
```

- [ ] **Step 5: Prune DevcontainerDetail.test.tsx**

In `apps/web/src/routes/__tests__/DevcontainerDetail.test.tsx`:
- Remove `listInboxEvents`, `resolveAgentSessionApproval`, `sendAgentSessionUserInput` from the endpoints import (line 6).
- Remove the mock decls `mockListInboxEvents`, `mockResolveApproval`, `mockSendUserInput` (lines ~20-22).
- Delete every intervention test block and its helpers/fixtures: the "AC1/AC2/AC3/AC4/AC5" inline-intervention tests (renders inline approval/question card, Approve/Reject/Send answer, awaiting state, unmount-on-resolve, no-card, listInboxEvents-with-filter), the test data `approvalEvent`, `questionEvent`, `waitingSession`, and the `openWaitingPanel()` helper.
- Delete the test `it('AC3: badge leaves waiting_for_approval after agent_sessions invalidation', …)`.
- Keep ALL composer / transcript / SSE-invalidation / live-stream tests.

Locate with: `grep -n "Inbox\|Approval\|Intervention\|intervention\|waiting_for_approval\|UserInput\|pendingIntervention" src/routes/__tests__/DevcontainerDetail.test.tsx`

- [ ] **Step 6: Verify**

Run: `pnpm test src/routes/__tests__/DevcontainerDetail.test.tsx`
Expected: PASS.
Then `grep -n "inbox\|approval\|waiting_for_approval\|InlineInterventionCard\|isBlocking" src/routes/DevcontainerDetail.tsx` → expect zero.

> Note: full `pnpm test` will still have failures elsewhere until later tasks (endpoints/types/mock still reference removed-from-UI things) — that's expected. Only the detail-page test must pass here.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(web): remove inline intervention/inbox seams from detail page"
```

---

### Task 2: Delete Inbox & Approvals route pages and navigation

**Files:**
- Delete: `apps/web/src/routes/Inbox.tsx`, `Approvals.tsx`, `inboxViews.ts`
- Delete: `apps/web/src/routes/__tests__/Inbox.test.tsx`, `Approvals.test.tsx`, `inboxViews.test.ts`
- Modify: `apps/web/src/routes/router.tsx`, `apps/web/src/components/Sidebar.tsx`

- [ ] **Step 1: Delete pages + route tests**

```bash
cd apps/web
git rm src/routes/Inbox.tsx src/routes/Approvals.tsx src/routes/inboxViews.ts \
  src/routes/__tests__/Inbox.test.tsx src/routes/__tests__/Approvals.test.tsx \
  src/routes/__tests__/inboxViews.test.ts
```

- [ ] **Step 2: Trim router.tsx**

Remove the `import { Inbox } from './Inbox'` and `import { Approvals } from './Approvals'` lines, and the `{ path: 'inbox', Component: Inbox }` and `{ path: 'approvals', Component: Approvals }` route entries. The child routes become: index redirect → `/devcontainers`, `devcontainers`, `devcontainers/:id`, `settings`, the dev-only `mock` route, and the `*` catch-all redirect. (Match the existing file's structure; only those 2 imports + 2 routes are removed.)

- [ ] **Step 3: Trim Sidebar.tsx ITEMS**

The nav items array becomes exactly:
```tsx
const ITEMS = [
  { to: '/devcontainers', label: 'Devcontainers' },
  { to: '/settings', label: 'Settings' },
] as const
```

- [ ] **Step 4: Verify**

Run: `grep -rn "Inbox\|Approvals\|inboxViews" src/routes/router.tsx src/components/Sidebar.tsx` → zero.
Run: `pnpm test src/routes/__tests__/Devcontainers.test.tsx src/routes/__tests__/DevcontainerDetail.test.tsx` → PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(web): remove Inbox & Approvals route pages and nav"
```

---

### Task 3: Delete the lib/intervention module

After Tasks 1-2, the only importers of `lib/intervention` (DevcontainerDetail, Inbox, Approvals) are gone.

**Files:**
- Delete: `apps/web/src/lib/intervention/` (entire directory)

- [ ] **Step 1: Confirm no importers remain**

Run: `grep -rn "lib/intervention\|from '\.\./intervention\|from '\./intervention" src --include=*.ts --include=*.tsx | grep -v "src/lib/intervention/"`
Expected: zero matches. (If any remain, STOP — an earlier task missed a consumer.)

- [ ] **Step 2: Delete**

```bash
git rm -r src/lib/intervention
```

- [ ] **Step 3: Verify**

Run: `grep -rn "intervention" src` → zero.
Run: `pnpm test src/routes/__tests__/DevcontainerDetail.test.tsx` → PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(web): remove intervention module"
```

---

### Task 4: Trim the API layer (endpoints + types)

**Files:**
- Modify: `apps/web/src/lib/api/endpoints.ts`, `types.ts`, `__tests__/endpoints.test.ts`

- [ ] **Step 1: Remove endpoint functions**

In `endpoints.ts` delete these exported functions: `listInboxEvents`, `fetchInboxEvent`, `markInboxEventRead`, `resolveInboxEvent`, `listApprovalRequests`, `fetchApprovalRequest`, `sendAgentSessionUserInput`, `resolveAgentSessionApproval`. After deletion, if the `buildQuery` helper is now unused, delete it too (`grep -n "buildQuery" src/lib/api/endpoints.ts` → if only its own definition remains, remove it). Fix the `import type { … } from './types'` block: remove every now-unused name (`InboxEvent`, `InboxEventDetail`, `InboxEventList`, `ApprovalRequest`, `ApprovalRequestList`, `ApprovalStatus`, `AgentSessionApprovalBody`, `AgentSessionUserInputBody`). Keep the rest.

Verify: `grep -n "Inbox\|Approval\|UserInput\|approval\|inbox" src/lib/api/endpoints.ts` → zero.

- [ ] **Step 2: Remove DTO types + waiting_for_approval**

In `types.ts` delete: `AgentSessionUserInputBody`, `ApprovalResolution`, `AgentSessionApprovalBody`, `InboxEventType`, `InboxEventStatus`, `InboxEvent`, `InboxEventDetail`, `InboxEventList`, `ApprovalStatus`, `ApprovalRequest`, `ApprovalRequestList`. Remove `'waiting_for_approval'` from `AgentSessionStatus`:
```ts
export type AgentSessionStatus =
  | 'starting'
  | 'running'
  | 'completed'
  | 'failed'
  | 'stopped'
```
Verify: `grep -n "Inbox\|Approval\|waiting_for_approval" src/lib/api/types.ts` → zero.

- [ ] **Step 3: Prune endpoints.test.ts**

Remove every `describe`/`it` block and import name for the 8 deleted endpoints. Locate: `grep -n "Inbox\|Approval\|UserInput\|approval\|inbox\|user-input" src/lib/api/__tests__/endpoints.test.ts`. Keep surviving-endpoint tests.

- [ ] **Step 4: Verify**

Run: `pnpm test src/lib/api` → PASS.
(Full tsc still has expected failures in mock/* until Task 6/7 — fine here.)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(web): drop inbox/approval API endpoints and DTOs"
```

---

### Task 5: Shrink the SSE Scope type

**Files:**
- Modify: `apps/web/src/lib/events/types.ts`, `__tests__/coordinator.test.ts`, `__tests__/SseProvider.test.tsx`

- [ ] **Step 1: Narrow the union**

`types.ts` → `export type Scope = 'devcontainers' | 'agent_sessions' | 'runtime'`

- [ ] **Step 2: Retarget test scope literals**

In `coordinator.test.ts` and `SseProvider.test.tsx`, swap every `'inbox'`/`'approvals'` scope literal to a surviving scope (`'agent_sessions'`/`'runtime'`); keep each test meaningful and distinct, and rename any title that named a removed scope (e.g. "all 5 scopes" → "all 3 scopes", trimming the array to the 3 survivors). Do NOT delete these tests.

Locate: `grep -n "inbox\|approvals" src/lib/events/__tests__/coordinator.test.ts src/lib/events/__tests__/SseProvider.test.tsx`

- [ ] **Step 3: Verify**

Run: `pnpm test src/lib/events` → PASS. `grep -rn "inbox\|approvals" src/lib/events` → zero.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(web): narrow SSE Scope to devcontainers/agent_sessions/runtime"
```

---

### Task 6: Remove inbox/approval mock handlers + state

One commit so handlers and the state modules they import disappear together.

**Files:**
- Modify: `apps/web/src/mock/handlers.ts`
- Delete: `apps/web/src/mock/state/inbox.ts`, `state/approvals.ts`, `state/__tests__/inbox.test.ts`, `state/__tests__/approvals.test.ts`, `mock/__tests__/inbox.test.ts`, `mock/__tests__/approvals.test.ts`

- [ ] **Step 1: Strip handlers.ts**

Read `handlers.ts`, then: remove `import * as inbox from './state/inbox'` and `import * as approvals from './state/approvals'`; remove any inbox/approval-only type from the `import type` block (e.g. `AgentSessionApprovalBody`); delete the `inboxHandlers`, `approvalHandlers`, and `agentSessionActionHandlers` arrays (the user-input + approval-resolution routes); delete any helper that becomes unused (e.g. `stubSession` if present); remove the `...inboxHandlers`, `...approvalHandlers`, `...agentSessionActionHandlers` spreads from the exported `handlers` array. Keep the static GET routes + `...devcontainerHandlers`.

Verify: `grep -n "inbox\|approval\|stubSession\|user-input\|approval-resolution\|approval-requests\|inbox-events\|AgentSessionApprovalBody" src/mock/handlers.ts` → zero.

- [ ] **Step 2: Delete state + tests**

```bash
cd apps/web
git rm src/mock/state/inbox.ts src/mock/state/approvals.ts \
  src/mock/state/__tests__/inbox.test.ts src/mock/state/__tests__/approvals.test.ts \
  src/mock/__tests__/inbox.test.ts src/mock/__tests__/approvals.test.ts
```

- [ ] **Step 3: Verify**

Run: `pnpm test` (full). Expected: the ONLY remaining failures are the cross-cutting files cleaned in Task 9 (`handlers.test.ts`, `scenario.test.ts`, `events.test.ts`, `mockSseRefetch.test.tsx`) failing on removed inbox/approval refs or imports of deleted state. List exactly which fail and why. Any OTHER failure → STOP/BLOCKED. Otherwise commit.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(web): remove inbox/approval mock handlers and state"
```

---

### Task 7: Clean mock fixtures, seeds, active statuses

**Files:**
- Modify: `apps/web/src/mock/fixtures.ts`, `state/seeds.ts`, `state/agentSessions.ts`

- [ ] **Step 1: fixtures.ts** — delete the `inboxEvents` and `approvalRequests` exports and remove `InboxEventList`/`ApprovalRequestList` from the type import block.

- [ ] **Step 2: seeds.ts** — change `as-seed-0001` status `'waiting_for_approval'` → `'running'` (only that field). Update the top comment block to drop the "detail page, inbox, approvals / InboxEventDetail" mentions:
```ts
// Single source of truth for cross-module mock identities: a given devcontainer
// or agent-session id describes the same object everywhere. Modules that need
// richer shapes (DevcontainerView) layer their extra fields on top of these.
```
Update the comment above `seedAgentSessions` (drop the `waiting_for_approval` framing):
```ts
// dc-seed-0001 (my-webapp) carries a spread of statuses for inspection;
// dc-seed-0002 (api-service) has two; dc-seed-0003/0004 have none.
```

- [ ] **Step 3: agentSessions.ts** — `const ACTIVE_STATUSES = new Set(['starting', 'running'])`.

- [ ] **Step 4: Verify**

Run: `pnpm test src/mock/__tests__/agentSessions.test.ts` → PASS.
`grep -rn "inbox\|approval\|waiting_for_approval" src/mock/fixtures.ts src/mock/state/seeds.ts src/mock/state/agentSessions.ts` → zero.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(web): clean inbox/approval mock fixtures, seeds, active statuses"
```

---

### Task 8: Remove inbox/approvals from the mock control UI

**Files:**
- Modify: `apps/web/src/mock/RailMock.tsx`, `apps/web/src/routes/MockScenarios.tsx`

- [ ] **Step 1: RailMock.tsx** — `const SCOPES: Scope[] = ['devcontainers', 'agent_sessions', 'runtime']`.

- [ ] **Step 2: MockScenarios.tsx** — same `SCOPES`, and `SCOPE_DESC` becomes exactly:
```tsx
const SCOPE_DESC: Record<Scope, string> = {
  devcontainers: 'Triggers devcontainer list/detail refetch.',
  agent_sessions: 'Triggers agent session list refetch.',
  runtime: 'Triggers runtime status refetch.',
}
```

- [ ] **Step 3: Verify**

`grep -rn "inbox\|approval" src/mock/RailMock.tsx src/routes/MockScenarios.tsx` → zero.
Run: `pnpm test src/mock/__tests__/MockScenarios.test.tsx` → PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(web): drop inbox/approvals scope buttons from mock UI"
```

---

### Task 9: Prune residual inbox/approval references in cross-cutting tests

Brings the full suite + tsc back to green.

**Files:** `apps/web/src/mock/__tests__/handlers.test.ts`, `events.test.ts`, `mockSseRefetch.test.tsx`, `scenario.test.ts` (confirm via grep).

- [ ] **Step 1: Locate**

Run: `grep -rn "inbox\|approval\|waiting_for_approval" src`

- [ ] **Step 2: Prune (rules)**
- Import of a deleted module (`./state/inbox`/`approvals`) or `reset*` from it → remove the import + its `beforeEach` call.
- A whole `it`/`describe` exercising an inbox/approval endpoint/scope/state → delete it.
- A scope literal `'inbox'`/`'approvals'` used incidentally (arrays, `cbs` maps, "all N scopes") → remove/retarget to a surviving scope; rename "all 5 scopes" → "all 3 scopes".
- An assertion that handlers serve `/inbox-events` or `/approval-requests` → delete it.
Do not gut surviving tests into no-ops.

- [ ] **Step 3: Verify clean + green**

`grep -rn "inbox\|approval\|waiting_for_approval\|intervention" src` → ZERO.
Run: `pnpm test` → ALL green.
Run: `pnpm exec tsc -b` → zero errors.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test(web): remove residual inbox/approval test cases"
```

---

### Task 10: Update docs and final verification

**Files:** `apps/web/CLAUDE.md`, `apps/web/src/mock/README.md`

- [ ] **Step 1: CLAUDE.md** — drop `/inbox`, `/approvals` from the route table; drop `Inbox.tsx`/`Approvals.tsx` from the route-files line; drop `inbox`/`approvals` from the `state/` stores list; remove any other inbox/approval/intervention mention. Find: `grep -ni "inbox\|approval\|intervention" apps/web/CLAUDE.md`.

- [ ] **Step 2: mock/README.md** — remove `state/inbox.ts`/`state/approvals.ts` rows, `inboxHandlers`, `/inbox-events`, `/approval-requests`, `INBOX_EVENT_NOT_FOUND`, `APPROVAL_REQUEST_NOT_PENDING`, the inbox/approvals scope mentions, the "approve/reject" example action, and any inbox/approval walkthrough. Keep it coherent (devcontainers + agent-sessions state, 3 SSE scopes, session-stream sections stay). Find: `grep -ni "inbox\|approval" apps/web/src/mock/README.md`.

- [ ] **Step 3: Final gate** (from `apps/web`)
1. `pnpm build` → tsc + vite succeed, no type errors.
2. `pnpm test` → all green.
3. `grep -n "label:" src/components/Sidebar.tsx` → exactly Devcontainers + Settings.
4. From repo root: `grep -rn "inbox\|approval\|waiting_for_approval\|intervention" apps/web/src apps/web/CLAUDE.md apps/web/src/mock/README.md` → ZERO.
Paste each command's output.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs(web): drop inbox/approvals/interventions from frontend docs"
```

---

## Notes for the executor

- Run all frontend commands from `apps/web/`. Use `pnpm`.
- Do NOT touch `apps/web/src/lib/chat/`, `apps/web/src/lib/stream/`, or
  `apps/web/src/mock/agentSessionStreams.ts` — the chat / Session Stream must keep
  working. If a change there seems needed, STOP and report.
- Do NOT touch Python `src/` at the repo root — backend is a separate follow-up.
- If `tsc` flags a now-unused import/symbol after a removal, delete the orphan.
