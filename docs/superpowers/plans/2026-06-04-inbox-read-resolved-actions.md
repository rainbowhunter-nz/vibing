# Inbox Event read/resolved actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user mark an Inbox Event read (auto, on open) or resolved (explicit, any type) from the UI, backed by two new projection-mutation endpoints.

**Architecture:** Two RPC-style POST routes (`/inbox-events/{id}/read`, `/inbox-events/{id}/resolve`) write the inbox projection directly — per ADR-0002 this is the documented exception that does NOT write the event log. The repository gains `mark_read` (unread→read only); `resolve` already exists. The frontend fires read on detail-open and exposes a resolve `ActionButton`, refetching list + detail after each mutation. No SSE broadcast (VIB-69's job).

**Tech Stack:** FastAPI + SQLite (`vibing_api`), pytest; React + TS + Vite (`apps/web`), vitest.

Spec: `docs/superpowers/specs/2026-06-04-inbox-read-resolved-actions-design.md`

---

## File Structure

- `src/vibing_api/core/vocabularies.py` — add `InboxEventStatus` enum (modify).
- `src/vibing_api/repositories/inbox.py` — add `mark_read`; type `status` field (modify).
- `src/vibing_api/api/schemas/inbox.py` — type `status` with the enum (modify).
- `src/vibing_api/core/reducer.py` — use the enum for the literal `"unread"` (modify).
- `src/vibing_api/api/routes/inbox.py` — add two POST routes (modify).
- `tests/api/test_inbox_read_resolved.py` — repo + route tests (create).
- `apps/web/src/lib/api/endpoints.ts` — add `markInboxEventRead`, `resolveInboxEvent` (modify).
- `apps/web/src/lib/api/__tests__/endpoints.test.ts` — endpoint tests (modify).
- `apps/web/src/routes/Inbox.tsx` — auto-read on open + resolve button + list refetch wiring (modify).
- `apps/web/src/routes/__tests__/Inbox.test.tsx` — UI tests (modify).

---

## Task 1: Backend vocabulary + `mark_read` repository method

**Files:**
- Modify: `src/vibing_api/core/vocabularies.py`
- Modify: `src/vibing_api/repositories/inbox.py:8` (import), `:22` (dataclass field type), `:124-131` (add method near `resolve`)
- Modify: `src/vibing_api/api/schemas/inbox.py:6,17` (import + field type)
- Modify: `src/vibing_api/core/reducer.py:169` (`status="unread"` → enum)
- Test: `tests/api/test_inbox_read_resolved.py` (create)

- [ ] **Step 1: Write the failing repo tests**

Create `tests/api/test_inbox_read_resolved.py`:

```python
"""Tests for inbox-event read/resolved actions (VIB-75)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.core.schema import apply_schema
from vibing_api.core.vocabularies import InboxEventStatus
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.inbox import InboxRepository

# `client` and `db_path` fixtures come from tests/api/conftest.py.


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection)
    connection.commit()
    return connection


def _make_devcontainer(conn: sqlite3.Connection) -> str:
    return DevcontainerRepository(conn).create("dc", "/tmp/dc").id


class TestMarkRead:
    def test_marks_unread_to_read(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        event = repo.create(dc_id, "question", InboxEventStatus.UNREAD)
        conn.commit()
        updated = repo.mark_read(event.id)
        assert updated is not None
        assert updated.status == InboxEventStatus.READ

    def test_noop_on_resolved(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        event = repo.create(dc_id, "completion", InboxEventStatus.RESOLVED)
        conn.commit()
        updated = repo.mark_read(event.id)
        assert updated is not None
        assert updated.status == InboxEventStatus.RESOLVED

    def test_missing_returns_none(self, conn: sqlite3.Connection) -> None:
        assert InboxRepository(conn).mark_read("nope") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_inbox_read_resolved.py::TestMarkRead -q`
Expected: FAIL — `ImportError` for `InboxEventStatus` / `AttributeError: mark_read`.

- [ ] **Step 3: Add the `InboxEventStatus` enum**

In `src/vibing_api/core/vocabularies.py`, after `InboxEventType`:

```python
class InboxEventStatus(StrEnum):
    UNREAD = auto()
    READ = auto()
    RESOLVED = auto()
```

- [ ] **Step 4: Type the repo field and add `mark_read`**

In `src/vibing_api/repositories/inbox.py`, update the import on line 8:

```python
from vibing_api.core.vocabularies import InboxEventStatus, InboxEventType
```

Change the dataclass field (line 23) `status: str` → `status: InboxEventStatus`.

Add after the existing `resolve` method (end of class):

```python
    def mark_read(self, inbox_event_id: str) -> InboxEvent | None:
        current = self.get(inbox_event_id)
        if current is None:
            return None
        if current.status != InboxEventStatus.UNREAD:
            return current
        self._conn.execute(
            "UPDATE inbox_events SET status = 'read', updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), inbox_event_id),
        )
        return self.get(inbox_event_id)
```

- [ ] **Step 5: Type the schema + reducer**

In `src/vibing_api/api/schemas/inbox.py`, update the import (line 6) to add `InboxEventStatus`, and change `status: str` (line 17) → `status: InboxEventStatus`:

```python
from vibing_api.core.vocabularies import InboxEventStatus, InboxEventType
```

In `src/vibing_api/core/reducer.py:169`, change `status="unread",` → `status=InboxEventStatus.UNREAD,` and add `InboxEventStatus` to the existing `vibing_api.core.vocabularies` import in that file.

- [ ] **Step 6: Run tests + checks to verify they pass**

Run: `uv run pytest tests/api/test_inbox_read_resolved.py::TestMarkRead -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS, no type/lint errors.

- [ ] **Step 7: Commit**

```bash
git add src/vibing_api tests/api/test_inbox_read_resolved.py
git commit -m "VIB-75 add InboxEventStatus vocab + mark_read repo method"
```

---

## Task 2: Backend read/resolve routes

**Files:**
- Modify: `src/vibing_api/api/routes/inbox.py`
- Test: `tests/api/test_inbox_read_resolved.py` (extend)

- [ ] **Step 1: Write the failing route tests**

Append to `tests/api/test_inbox_read_resolved.py`:

```python
def _create_dc(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _seed_inbox(dc_id: str, status: str = "unread") -> str:
    with get_connection() as conn:
        event = InboxRepository(conn).create(dc_id, "question", status)
        conn.commit()
    return event.id


class TestReadRoute:
    def test_marks_read(self, client: TestClient) -> None:
        dc_id = _create_dc(client)
        event_id = _seed_inbox(dc_id, "unread")
        resp = client.post(f"/api/v1/inbox-events/{event_id}/read")
        assert resp.status_code == 200
        assert resp.json()["status"] == "read"

    def test_noop_on_resolved(self, client: TestClient) -> None:
        dc_id = _create_dc(client)
        event_id = _seed_inbox(dc_id, "resolved")
        resp = client.post(f"/api/v1/inbox-events/{event_id}/read")
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

    def test_unknown_id_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/inbox-events/nope/read")
        assert resp.status_code == 404


class TestResolveRoute:
    def test_marks_resolved(self, client: TestClient) -> None:
        dc_id = _create_dc(client)
        event_id = _seed_inbox(dc_id, "unread")
        resp = client.post(f"/api/v1/inbox-events/{event_id}/resolve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

    def test_unknown_id_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/inbox-events/nope/resolve")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_inbox_read_resolved.py -k Route -q`
Expected: FAIL — routes return 405/404 (method not allowed / no such route).

- [ ] **Step 3: Add the routes**

In `src/vibing_api/api/routes/inbox.py`, append after `get_inbox_event`. The
existing `resolve`/`mark_read` repo methods return `None` when the row is absent,
which we map to 404:

```python
@router.post("/{inbox_event_id}/read", response_model=InboxEvent)
def mark_inbox_event_read(inbox_event_id: str) -> InboxEvent:
    with get_connection() as conn:
        event = InboxRepository(conn).mark_read(inbox_event_id)
        if event is None:
            raise InboxEventNotFoundError(inbox_event_id)
        conn.commit()
    return InboxEvent.model_validate(event)


@router.post("/{inbox_event_id}/resolve", response_model=InboxEvent)
def resolve_inbox_event(inbox_event_id: str) -> InboxEvent:
    with get_connection() as conn:
        event = InboxRepository(conn).resolve(inbox_event_id)
        if event is None:
            raise InboxEventNotFoundError(inbox_event_id)
        conn.commit()
    return InboxEvent.model_validate(event)
```

- [ ] **Step 4: Run tests + checks to verify they pass**

Run: `uv run pytest tests/api/test_inbox_read_resolved.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/api/routes/inbox.py tests/api/test_inbox_read_resolved.py
git commit -m "VIB-75 add POST inbox-events read/resolve routes"
```

---

## Task 3: Frontend endpoint functions

**Files:**
- Modify: `apps/web/src/lib/api/endpoints.ts` (import block + after `fetchInboxEvent` on line 79)
- Test: `apps/web/src/lib/api/__tests__/endpoints.test.ts`

- [ ] **Step 1: Write the failing endpoint tests**

In `apps/web/src/lib/api/__tests__/endpoints.test.ts`, add `markInboxEventRead`
and `resolveInboxEvent` to the import block from `'../endpoints'`, then append:

```ts
const inboxEvent = {
  id: 'evt1',
  devcontainer_id: 'dc1',
  agent_session_id: null,
  approval_request_id: null,
  event_type: 'question',
  status: 'read',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('markInboxEventRead', () => {
  it('POSTs to /inbox-events/:id/read', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, inboxEvent))
    vi.stubGlobal('fetch', fetchMock)
    const result = await markInboxEventRead('evt1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/inbox-events/evt1/read',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result).toEqual(inboxEvent)
  })
})

describe('resolveInboxEvent', () => {
  it('POSTs to /inbox-events/:id/resolve', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, inboxEvent))
    vi.stubGlobal('fetch', fetchMock)
    const result = await resolveInboxEvent('evt1')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/inbox-events/evt1/resolve',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(result).toEqual(inboxEvent)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- endpoints`
Expected: FAIL — `markInboxEventRead`/`resolveInboxEvent` are not exported.

- [ ] **Step 3: Add the endpoint functions**

In `apps/web/src/lib/api/endpoints.ts`, add `InboxEvent` to the `import type`
block from `'./types'`, then add after `fetchInboxEvent` (line 79):

```ts
export const markInboxEventRead = (id: string): Promise<InboxEvent> =>
  sendJson<InboxEvent>(`/inbox-events/${encodeURIComponent(id)}/read`, 'POST') as Promise<InboxEvent>

export const resolveInboxEvent = (id: string): Promise<InboxEvent> =>
  sendJson<InboxEvent>(`/inbox-events/${encodeURIComponent(id)}/resolve`, 'POST') as Promise<InboxEvent>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm test -- endpoints`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/api/endpoints.ts apps/web/src/lib/api/__tests__/endpoints.test.ts
git commit -m "VIB-75 add markInboxEventRead/resolveInboxEvent endpoints"
```

---

## Task 4: Frontend auto-read + resolve UI

**Files:**
- Modify: `apps/web/src/routes/Inbox.tsx` (imports line 7-17; `InboxDetail`/`InboxDetailPanel` ~line 253-326; `Inbox` selection wiring ~line 386-389)
- Test: `apps/web/src/routes/__tests__/Inbox.test.tsx`

- [ ] **Step 1: Write the failing UI tests**

In `apps/web/src/routes/__tests__/Inbox.test.tsx`, add `markInboxEventRead` and
`resolveInboxEvent` to the import from `'../../lib/api'`, register mocks beside
the others, then append these tests (follow the file's existing
render/`waitFor` helpers; an `unread` question detail and a `resolved` one):

```ts
const unreadDetail: InboxEventDetail = {
  id: 'evt1', devcontainer_id: 'dc1', agent_session_id: null, approval_request_id: null,
  event_type: 'question', status: 'unread', created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z', content: 'Pick a name?',
  devcontainer: { id: 'dc1', name: 'env', local_path: '/w', status: 'running',
    created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
  agent_session: null, approval_request: null,
}

it('fires markInboxEventRead when opening an unread event', async () => {
  mockList.mockResolvedValue({ items: [{ ...unreadDetail }] as InboxEvent[] })
  mockDetail.mockResolvedValue(unreadDetail)
  mockRead.mockResolvedValue({ ...unreadDetail, status: 'read' } as InboxEvent)
  render(
    <MemoryRouter initialEntries={['/inbox?selected=evt1']}>
      <SseProvider><Inbox /></SseProvider>
    </MemoryRouter>,
  )
  await waitFor(() => expect(mockRead).toHaveBeenCalledWith('evt1'))
})

it('does not fire markInboxEventRead for a read event', async () => {
  const readDetail = { ...unreadDetail, status: 'read' as const }
  mockList.mockResolvedValue({ items: [readDetail] as InboxEvent[] })
  mockDetail.mockResolvedValue(readDetail)
  render(
    <MemoryRouter initialEntries={['/inbox?selected=evt1']}>
      <SseProvider><Inbox /></SseProvider>
    </MemoryRouter>,
  )
  await screen.findByText('Pick a name?')
  expect(mockRead).not.toHaveBeenCalled()
})

it('resolves an event when the resolve button is clicked', async () => {
  mockList.mockResolvedValue({ items: [{ ...unreadDetail }] as InboxEvent[] })
  mockDetail.mockResolvedValue(unreadDetail)
  mockRead.mockResolvedValue({ ...unreadDetail, status: 'read' } as InboxEvent)
  mockResolveInbox.mockResolvedValue({ ...unreadDetail, status: 'resolved' } as InboxEvent)
  render(
    <MemoryRouter initialEntries={['/inbox?selected=evt1']}>
      <SseProvider><Inbox /></SseProvider>
    </MemoryRouter>,
  )
  const btn = await screen.findByRole('button', { name: /resolve/i })
  await userEvent.click(btn)
  await waitFor(() => expect(mockResolveInbox).toHaveBeenCalledWith('evt1'))
})
```

Add the mock handles near the other `vi.mocked(...)` lines:

```ts
const mockRead = vi.mocked(markInboxEventRead)
const mockResolveInbox = vi.mocked(resolveInboxEvent)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && pnpm test -- Inbox`
Expected: FAIL — no resolve button; `markInboxEventRead` never called.

- [ ] **Step 3: Wire auto-read + onChanged through the detail panel**

In `apps/web/src/routes/Inbox.tsx`:

Add to the `'../lib/api'` import block: `markInboxEventRead`, `resolveInboxEvent`.

Replace `InboxDetailPanel` (line 313-326) so it accepts `onChanged`, fires
auto-read once when the loaded detail is `unread`, and passes a resolve handler
down:

```tsx
function InboxDetailPanel({
  id,
  onClose,
  onChanged,
}: {
  id: string
  onClose: () => void
  onChanged: () => void
}) {
  const { state, refetch } = useApiQuery(() => fetchInboxEvent(id), [id])
  const { register } = useSseInvalidation()

  useEffect(() => register('inbox', refetch), [register, refetch])
  useEffect(() => register('agent_sessions', refetch), [register, refetch])
  useEffect(() => register('approvals', refetch), [register, refetch])

  useEffect(() => {
    if (state.kind === 'ready' && state.data.status === 'unread') {
      void markInboxEventRead(state.data.id).then(() => {
        refetch()
        onChanged()
      })
    }
  }, [state, refetch, onChanged])

  const resolve = () =>
    resolveInboxEvent(id).then(() => {
      refetch()
      onChanged()
    })

  return (
    <QueryBoundary state={state} error={detailErrorElement(state)}>
      {(detail) => <InboxDetail detail={detail} onClose={onClose} onResolve={resolve} />}
    </QueryBoundary>
  )
}
```

- [ ] **Step 4: Add the resolve control to `InboxDetail`**

In `apps/web/src/routes/Inbox.tsx`, change `InboxDetail`'s signature (line 253)
to accept `onResolve`, and render a resolve `ActionButton` (already imported)
when not resolved, plus a "Resolved" marker when it is. Insert at the top of the
returned tree, right after the header block (`MetaLine`, line 270):

```tsx
function InboxDetail({
  detail,
  onClose,
  onResolve,
}: {
  detail: InboxEventDetail
  onClose: () => void
  onResolve: () => void
}) {
```

Then after `<MetaLine detail={detail} />`:

```tsx
      <div className="mb-2 flex justify-end px-4">
        {detail.status === 'resolved' ? (
          <span className="text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">
            Resolved
          </span>
        ) : (
          <ActionButton label="Resolve" onClick={onResolve} variant="reject" />
        )}
      </div>
```

- [ ] **Step 5: Pass `onChanged` from `Inbox`**

In `apps/web/src/routes/Inbox.tsx`, the `Inbox` component already holds the list
`refetch` (line 332). Update the detail render (line 388):

```tsx
            <InboxDetailPanel key={selectedId} id={selectedId} onClose={clearSelection} onChanged={refetch} />
```

- [ ] **Step 6: Run tests + checks to verify they pass**

Run: `cd apps/web && pnpm test -- Inbox && pnpm test -- endpoints && pnpm build`
Expected: PASS, type-check clean.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/routes/Inbox.tsx apps/web/src/routes/__tests__/Inbox.test.tsx
git commit -m "VIB-75 auto-read on open + resolve action in Inbox UI"
```

---

## Task 5: Full verification

- [ ] **Step 1: Backend suite + checks**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 2: Frontend suite + build**

Run: `cd apps/web && pnpm test && pnpm build`
Expected: all PASS.

- [ ] **Step 3: Confirm acceptance criteria**

- User can mark read → auto on detail open (Task 4).
- User can mark resolved → resolve button (Task 4).
- Backend mutation endpoints added (Task 2).
- State reflects in place → refetch on success (Task 4).
- Tests cover read + resolve → Tasks 1-4.
