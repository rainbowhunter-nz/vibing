# Approvals workbench — design

**Ticket:** VIB-48
**Date:** 2026-06-04
**Status:** Approved

## Problem

The web Approvals page is a placeholder empty state. It should become a focused workbench for
pending approval decisions and historical review: users see pending Approval Requests, approve or
reject them inline, and inspect approved/rejected history. Status must update live (no browser
refresh) when SSE invalidations arrive. The read APIs (VIB-39) and the session-scoped
approval-resolution endpoint (VIB-41) already exist.

## Backend constraints (ground truth)

From `apps/web/src/lib/api/{types,endpoints}.ts` and `src/vibing_api`:

- `ApprovalRequest`: `id`, `devcontainer_id`, `agent_session_id`, `status`
  (`pending` | `approved` | `rejected`), `requested_action`, `created_at`, `decided_at`.
- `listApprovalRequests({ status?, devcontainerId? })` — filters by a **single** status and/or
  devcontainer. Returns `{ items }`.
- `resolveAgentSessionApproval(devcontainerId, sessionId, { approval_request_id, resolution })` —
  the session-scoped resolution endpoint. `resolution` is `'approved' | 'rejected'`.
- **Resolution is asynchronous.** The endpoint returns **202** with the *unchanged* AgentSession
  (approval stays `pending`); it forwards a `RESOLVE_APPROVAL` command to the runtime. The actual
  `approved`/`rejected` status lands later via runtime event → projection → SSE `approvals`
  invalidation → refetch.
- Resolution errors:
  - `APPROVAL_REQUEST_NOT_PENDING` (409) — already handled (the **stale** case).
  - `APPROVAL_REQUEST_NOT_FOUND` (404) — missing or belongs to another session.
  - Plus `RUNTIME_UNAVAILABLE`, inactive/not-found agent session, devcontainer not found.

Implication: **no backend, `types.ts`, or `endpoints.ts` changes are needed.** Unlike the Inbox
(VIB-47), the API supports a status filter, so the three views are server-side fetches, not
client-side derivations.

## Decisions

| Question | Decision |
|----------|----------|
| Layout | **Single-column queue** with inline per-row actions (not a split-pane; no detail panel) |
| Tabs | **Pending** (default) / **Approved** / **Rejected** — each a server-side `status` fetch |
| History presentation | Three separate status tabs, not a merged "History" tab (1:1 with API) |
| Post-202 state | **Honest "Submitted · awaiting runtime"** — row stays `pending`; no optimistic flip |
| Devcontainer filter | **None** — not in the ACs (YAGNI) |
| Route | Existing `/approvals`; no router change |

## Layout & components

All inline in `apps/web/src/routes/Approvals.tsx`, mirroring `Inbox.tsx`.

- **`PageHeader`** — title "Approvals"; crumb = the active tab's item count (e.g. "2 pending" on
  the default tab), from the loaded list. One query, no speculative second fetch.
- **Tabs** — `Pending` / `Approved` / `Rejected`. Active tab is local `useState`. Each tab drives
  `listApprovalRequests({ status })`; switching tabs swaps the query input.
- **List** — one scrollable column. Each row shows `requested_action`, a status badge, devcontainer
  id, short `agent_session_id`, and relative `created_at`. Pending rows additionally render inline
  **Approve / Reject** controls.
- **Per-tab empty states** via `EmptyState` ("No pending approvals" / "No approved requests yet" /
  "No rejected requests").
- Reuse `QueryBoundary`, `ErrorState`, `loadError('approvals')`, `formatRelativeTime`, `cn`. A small
  status-badge-class helper stays local to the route (per-domain status vocabulary, like Inbox).

## Action flow (`PendingRow` local state machine)

Each pending row owns its own state; the surrounding list query is unaffected until SSE refetch.

1. **idle** — Approve/Reject enabled.
2. click → **in-flight** — both controls disabled, "⟳ Approving…/Rejecting…". Calls
   `resolveAgentSessionApproval(devcontainer_id, agent_session_id, { approval_request_id, resolution })`.
3. **202** → **awaiting** — "✓ Submitted · awaiting runtime"; row still shows `pending`. No
   optimistic status flip.
4. SSE `approvals` invalidation → list refetch → the now-`approved`/`rejected` request leaves the
   Pending list and appears under its tab.

## Errors

- **`APPROVAL_REQUEST_NOT_PENDING` (409, stale)** → inline red message "Already resolved elsewhere —
  no longer pending." Controls stay disabled; the next SSE refetch drops the row.
- **Any other resolution failure** (`RUNTIME_UNAVAILABLE`, inactive/not-found session, etc.) → inline
  "Couldn't submit — try again" and **re-enable** the controls for retry.
- Inline errors live on the row, not as a page-level boundary.

## Live updates (SSE)

The list query registers `approvals`, `inbox`, `agent_sessions` → `refetch` (same trio as Inbox).
A pending row resolving elsewhere, a runtime confirming a resolution, and a new pending request all
reconcile in place without browser refresh. Refresh-only status behavior is treated as a bug.

## Router / API / types

No changes. `/approvals` already maps to `Approvals` in `router.tsx`. `listApprovalRequests`,
`resolveAgentSessionApproval`, and the `ApprovalRequest` / `ApprovalResolution` types already exist.

## Testing

`apps/web/src/routes/__tests__/Approvals.test.tsx` (mirroring `Inbox.test.tsx`):

- loading spinner, error state, per-tab empty states.
- Pending is the default tab and fetches `status=pending`.
- Approved / Rejected tabs fetch and render their respective histories.
- Approve calls `resolveAgentSessionApproval` with the row's `devcontainer_id`, `agent_session_id`,
  `approval_request_id`, and `resolution: 'approved'`; Reject with `'rejected'`.
- in-flight disables both controls.
- 202 shows the "Submitted · awaiting" state and does **not** flip the row to approved/rejected.
- stale 409 (`APPROVAL_REQUEST_NOT_PENDING`) shows the inline stale error.
- a non-stale failure shows the retry error and re-enables controls.
- SSE `approvals` invalidation flips a row's status / drops it from the Pending list without refresh.

## Out of scope

- Backend / API / type changes (none required).
- Live toasts (separate ticket).
- Devcontainer or text filtering.
