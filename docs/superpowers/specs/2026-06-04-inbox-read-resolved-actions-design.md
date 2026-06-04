# VIB-75 — Inbox Event read/resolved actions

## Goal

Let a user mark an Inbox Event **read** or **resolved** from the UI, adding the
backend mutation endpoints these actions need. State reflects in place after the
action.

Per ADR-0002, marking an item read/resolved is the documented exception to
event-sourcing: a **direct mutation of the inbox projection** that does **not**
write the event log. Keep that boundary.

This is feature work, **not** a live-update slice. "Reflects in place" means the
acting client refetches after the mutation — no SSE broadcast, no cross-client
sync. That is VIB-69's job; this ticket is its prerequisite.

## Status model

`inbox_events.status` is a single linear field: `unread → read → resolved`.

- **read** is reached automatically when a user opens an event's detail.
- **resolved** is reached by an explicit action, available on every event type
  (manual dismiss/archive). `resolved` is terminal.
- Opening a `read` or `resolved` event does not change its status (no downgrade).

## Backend

### Vocabulary — `core/vocabularies.py`

Add a typed vocabulary (ADR-0002: projected vocabularies should be typed enums,
not bare strings):

```python
class InboxEventStatus(StrEnum):
    UNREAD = auto()
    READ = auto()
    RESOLVED = auto()
```

Type the `status` field with it in the repository dataclass and
`api/schemas/inbox.py`. The reducer's `status="unread"` becomes
`InboxEventStatus.UNREAD`.

### Repository — `repositories/inbox.py`

- Add `mark_read(id) -> InboxEvent | None`: returns `None` if the row is absent;
  sets `status='read'` **only when currently `unread`** (leaves `resolved`
  untouched), bumps `updated_at`, returns the updated row.
- Reuse the existing `resolve(id)` for the resolve endpoint (already idempotent,
  already used by the reducer's event-projection path).

### Routes — `api/routes/inbox.py`

```
POST /inbox-events/{id}/read     → InboxEvent
POST /inbox-events/{id}/resolve  → InboxEvent
```

- Both commit and return the updated `InboxEvent`.
- Absent id → `404 InboxEventNotFound` (existing `InboxEventNotFoundError`).
- Idempotent: re-calling `read` on a read/resolved item, or `resolve` on a
  resolved item, is a no-op that returns current state.
- No SSE broadcast (out of scope).

These follow the codebase's existing RPC-action convention (`.../user-input`,
`.../approval` are POST verbs returning the updated resource).

## Frontend

### API layer — `lib/api/endpoints.ts` + `types.ts`

```ts
markInboxEventRead(id: string): Promise<InboxEvent>   // POST .../read
resolveInboxEvent(id: string): Promise<InboxEvent>    // POST .../resolve
```

Plain `sendJson` calls. No `useInterventionAction` — that machinery models
runtime round-trips (submit → await runtime event → stale detection), which do
not exist for a synchronous local projection write.

### UI — `routes/Inbox.tsx`

- `Inbox` passes an `onChanged` callback (the list's `refetch`) into
  `InboxDetailPanel`.
- **Auto-read:** in `InboxDetailPanel`, a `useEffect` keyed on the loaded detail
  fires `markInboxEventRead(id)` once when `detail.status === 'unread'`, then
  `refetch()` + `onChanged()`.
- **Resolve:** an `ActionButton` in `InboxDetail` (plain `await` + refetch).
  Hidden when `detail.status === 'resolved'`; resolved items show a "Resolved"
  marker. The item stays selected after resolve (mirrors how `ApprovalControls`
  hides actions once resolved).
- List rows already render `event.status`, so read/resolved reflect after the
  list refetch.

## Tests

**`tests/api`**

- `read` marks `unread → read`.
- `read` is a no-op on a `resolved` event (stays `resolved`).
- `resolve` sets `resolved`.
- `read` and `resolve` return `404` for an unknown id.

**`apps/web`**

- Opening an `unread` detail fires `markInboxEventRead` and refetches list +
  detail.
- Opening a `read`/`resolved` detail does **not** fire `markInboxEventRead`.
- Resolve button calls `resolveInboxEvent`, hides after resolve, refreshes the
  list.

## Out of scope (VIB-69)

- SSE broadcast / cross-client live update of read/resolved state.
- A "mark unread" / un-resolve toggle.
