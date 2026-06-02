# Inbox triage list & detail panel — design

**Ticket:** VIB-47
**Date:** 2026-06-03
**Status:** Approved

## Problem

The web Inbox is a placeholder empty state. It should become the main triage workflow:
users see items needing attention, select an Inbox Event, inspect it in a side panel, and
watch Inbox status change live (no browser refresh). The read APIs already exist (VIB-39).

## Backend constraints (ground truth)

From `apps/web/src/lib/api/types.ts` and `src/vibing_api`:

- `InboxEvent`: `id`, `devcontainer_id`, `agent_session_id?`, `approval_request_id?`,
  `event_type` (`question` | `approval_request` | `completion` | `failure`),
  `status` (free-form string; observed values `unread`, `read`, `resolved`),
  `created_at`, `updated_at`.
- `InboxEventDetail` extends `InboxEvent` with embedded `devcontainer`, `agent_session?`,
  `approval_request?`.
- `listInboxEvents(filters?)` — filters by `status` / `devcontainer_id` / `agent_session_id`
  only. **No `event_type` filter and no multi-status filter.** Returns rows ordered by
  `created_at` ascending.
- `fetchInboxEvent(id)` — returns `InboxEventDetail`; throws `INBOX_EVENT_NOT_FOUND` when
  absent.

Implication: **the two views (Needs Attention / All) and their ordering are derived
client-side** from a single unfiltered list fetch.

## Approach

Single `/inbox` route, persistent split-pane (list left, detail right), selection encoded as
a `?selected=<id>` query param. Two parallel queries (list + detail), both refetched on SSE
invalidation. Rejected alternatives: nested `/inbox/:id` routes (contradicts the AC's
query-param requirement); a client-side detail cache (speculative, YAGNI).

## Decisions

| Question | Decision |
|----------|----------|
| Layout | **Persistent split-pane** — list always left, detail fills the right pane |
| Selection encoding | **`/inbox?selected=<inbox_event_id>`** via `useSearchParams` |
| Needs Attention filter | Exclude `completion` **and** any `status === 'resolved'` |
| View tab state | **Local** `useState` (not in URL; only `selected` must survive refresh) |
| Scope of this ticket | **Read-only** display — actions are VIB-50, toasts are VIB-52 |

## Views (pure, client-side)

Both derived from the single fetched list:

- **Needs Attention** (default tab): drop `event_type === 'completion'` and any event with
  `status === 'resolved'`. Order: blocking group (`question`, `approval_request`) first, then
  `failure`; newest-first (`created_at` desc) within each group.
- **All**: every event, newest-first, no filtering.

Implemented as pure helpers `(events: InboxEvent[]) => InboxEvent[]` so they unit-test
without rendering.

## Layout & components

All inline in `apps/web/src/routes/Inbox.tsx`, mirroring how `Devcontainers.tsx` keeps
`DevcontainerTable` local.

- **`PageHeader`** — title "Inbox"; crumb = needs-attention count (e.g. "3 need attention").
- **View tabs** — `Needs Attention` / `All` toggle.
- **List (left pane)** — one selectable row per event:
  - event-type badge, devcontainer name, agent-session id (short), relative time, status.
  - selected row highlighted with the left-accent-border idiom used in the devcontainer table.
  - group labels ("Blocking" / "Failures") shown in the Needs Attention view.
- **`InboxDetailPanel({ id })` (right pane)** — rendered only when `selected` is set, so its
  query mounts only with a selection. Runs `fetchInboxEvent(id)`; renders type, status,
  devcontainer, agent session, approval request, created time. Read-only.
- **Empty selection** — right pane shows a "Select an item" hint when nothing is selected.
- Reuse `QueryBoundary`, `EmptyState`, `ErrorState`, `loadError('inbox')`.

## Selection & routing

`useSearchParams()` for `selected`. Row click sets `?selected=<id>`; a close/deselect control
clears it. The param is read on mount, so a selection survives refresh. A `selected` id that
no longer exists surfaces the detail panel's not-found error (does not break the list).

## Live updates (SSE)

- List query registers `inbox`, `agent_sessions`, `approvals` → `refetch`.
- `InboxDetailPanel` registers the same three scopes → refetch its own detail.

So both a row's status badge and the open detail update in place on an `invalidate` event,
satisfying "list rows and selected detail status update without browser refresh." Refresh-only
status behavior is treated as a bug.

## Shared util cleanup

`formatRelativeTime` currently lives in `Devcontainers.tsx`. Extract it to
`apps/web/src/lib/time.ts`; both `Devcontainers` and `Inbox` import it (avoids duplication per
project rules). Badge-class helpers stay per-route since each domain's status vocabulary differs.

## Router

No change needed — `/inbox` already maps to `Inbox` in `router.tsx`. The route is a single
component; `?selected=` is a query param, not a new route entry.

## API / types

No changes. `listInboxEvents`, `fetchInboxEvent`, `InboxEvent`, and `InboxEventDetail` already
exist.

## Out of scope (future tickets)

- **Intervention actions** (answer question / approve / reject) — VIB-50.
- **Live toasts** — VIB-52.

## Testing

`apps/web/src/routes/__tests__/Inbox.test.tsx` (mirroring `Devcontainers.test.tsx`):

- loading spinner, empty state, error state, list render.
- Needs Attention ordering: blocking (question, approval_request) before failure.
- Needs Attention excludes completions and `resolved` events; All includes them.
- click-to-select sets `?selected=<id>` and renders the detail panel.
- initial `?selected=<id>` renders the detail on load (survives refresh).
- SSE `invalidate` on `inbox` updates a list row's status without refresh.
- SSE `invalidate` updates the open detail's status without refresh.

Pure-helper unit tests for the Needs Attention / All filtering + ordering.
