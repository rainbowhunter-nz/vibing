# Inbox User Intervention Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users answer questions and approve/reject approval requests directly from the Inbox detail panel, with immediate sending/accepted/resolved feedback.

**Architecture:** Backend persists the question prompt so the panel can show it (new `inbox_events.content` column, captured by the reducer from the `agent_asked_question` payload). Frontend extracts the action state machine (today inline in `Approvals.tsx`) into a shared `src/lib/intervention/` module, then rewrites the Inbox detail panel to a conversational layout that composes it. `Approvals.tsx` is refactored onto the same module.

**Tech Stack:** Python (FastAPI, SQLite, Pydantic, pytest); React + TypeScript + Vite + Tailwind; Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-06-04-inbox-user-intervention-actions-design.md`

---

## File Structure

**Backend (modify):**
- `src/vibing_api/core/schema.py` — add `content` column, bump `SCHEMA_VERSION`.
- `src/vibing_api/repositories/inbox.py` — persist/return `content`.
- `src/vibing_api/core/reducer.py` — capture `payload["question"]` into `content`.
- `src/vibing_api/api/schemas/inbox.py` — expose `content` on `InboxEventDetail`.
- `src/vibing_api/dev/sample_data.py` — sample question `content`.

**Frontend (create):**
- `apps/web/src/lib/intervention/useInterventionAction.ts` — action state machine hook.
- `apps/web/src/lib/intervention/ActionButton.tsx` — single styled action button (moved from Approvals).
- `apps/web/src/lib/intervention/StatusNote.tsx` — awaiting/stale/error note.
- `apps/web/src/lib/intervention/index.ts` — barrel.

**Frontend (modify):**
- `apps/web/src/lib/api/types.ts` — `content` on `InboxEventDetail`.
- `apps/web/src/routes/Approvals.tsx` — consume the shared module.
- `apps/web/src/routes/Inbox.tsx` — conversational detail panel + controls.

**Tests:** `tests/api/test_reducer.py`, `tests/api/test_inbox_approvals.py`, `apps/web/src/routes/__tests__/Inbox.test.tsx`, `apps/web/src/routes/__tests__/Approvals.test.tsx`.

---

## Task 1: Add `content` column to the inbox schema

**Files:**
- Modify: `src/vibing_api/core/schema.py`

- [ ] **Step 1: Add the column and bump the version**

In `src/vibing_api/core/schema.py`, change `SCHEMA_VERSION = "2"` to:

```python
SCHEMA_VERSION = "3"
```

In the `inbox_events` `CREATE TABLE` statement, add a `content` column after `status`:

```python
    """
    CREATE TABLE IF NOT EXISTS inbox_events (
        id TEXT PRIMARY KEY,
        devcontainer_id TEXT NOT NULL REFERENCES devcontainers(id) ON DELETE CASCADE,
        agent_session_id TEXT REFERENCES agent_sessions(id) ON DELETE CASCADE,
        approval_request_id TEXT REFERENCES approval_requests(id) ON DELETE SET NULL,
        event_type TEXT NOT NULL,
        status TEXT NOT NULL,
        content TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
```

- [ ] **Step 2: Verify it applies to a fresh DB**

Run: `uv run python -c "import sqlite3; from vibing_api.core.schema import apply_schema; c=sqlite3.connect(':memory:'); apply_schema(c); print([r[1] for r in c.execute('PRAGMA table_info(inbox_events)')])"`
Expected: the printed column list includes `content`.

> Note: there is no migration runner (`apply_schema` is `CREATE TABLE IF NOT EXISTS`). Existing dev DBs must be recreated — delete the sqlite file pointed to by `settings.database_url`.

- [ ] **Step 3: Commit**

```bash
git add src/vibing_api/core/schema.py
git commit -m "VIB-50 add inbox_events.content column"
```

---

## Task 2: Persist and return `content` in the inbox repository

**Files:**
- Modify: `src/vibing_api/repositories/inbox.py`
- Test: `tests/api/test_inbox_approvals.py`

- [ ] **Step 1: Write the failing test**

In `tests/api/test_inbox_approvals.py`, inside `class TestInboxRepository`, add:

```python
    def test_create_stores_content(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        created = repo.create(dc_id, "question", "unread", content="Redis or in-memory?")
        conn.commit()
        got = repo.get(created.id)
        assert got is not None
        assert got.content == "Redis or in-memory?"

    def test_create_content_defaults_none(self, conn: sqlite3.Connection) -> None:
        dc_id = _make_devcontainer(conn)
        repo = InboxRepository(conn)
        created = repo.create(dc_id, "completion", "unread")
        conn.commit()
        got = repo.get(created.id)
        assert got is not None
        assert got.content is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_inbox_approvals.py::TestInboxRepository::test_create_stores_content -v`
Expected: FAIL — `create()` got an unexpected keyword argument `content` (or `InboxEvent` has no attribute `content`).

- [ ] **Step 3: Implement**

In `src/vibing_api/repositories/inbox.py`:

Update `_COLUMNS`:

```python
_COLUMNS = (
    "id, devcontainer_id, agent_session_id, approval_request_id, "
    "event_type, status, content, created_at, updated_at"
)
```

Add `content` to the dataclass (after `status`):

```python
@dataclass(frozen=True)
class InboxEvent:
    id: str
    devcontainer_id: str
    agent_session_id: str | None
    approval_request_id: str | None
    event_type: InboxEventType
    status: str
    content: str | None
    created_at: str
    updated_at: str
```

Update `_row_to_inbox` to read it:

```python
def _row_to_inbox(row: sqlite3.Row) -> InboxEvent:
    return InboxEvent(
        id=row["id"],
        devcontainer_id=row["devcontainer_id"],
        agent_session_id=row["agent_session_id"],
        approval_request_id=row["approval_request_id"],
        event_type=row["event_type"],
        status=row["status"],
        content=row["content"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
```

Update `create()` — add the parameter, set it on the dataclass, and add it to the INSERT values:

```python
    def create(
        self,
        devcontainer_id: str,
        event_type: InboxEventType,
        status: str,
        agent_session_id: str | None = None,
        approval_request_id: str | None = None,
        content: str | None = None,
    ) -> InboxEvent:
        now = datetime.now(timezone.utc).isoformat()
        event = InboxEvent(
            id=str(uuid.uuid4()),
            devcontainer_id=devcontainer_id,
            agent_session_id=agent_session_id,
            approval_request_id=approval_request_id,
            event_type=event_type,
            status=status,
            content=content,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            f"INSERT INTO inbox_events ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.devcontainer_id,
                event.agent_session_id,
                event.approval_request_id,
                event.event_type,
                event.status,
                event.content,
                event.created_at,
                event.updated_at,
            ),
        )
        return event
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_inbox_approvals.py -q`
Expected: PASS (new tests pass; existing repo tests still pass — `content` defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/repositories/inbox.py tests/api/test_inbox_approvals.py
git commit -m "VIB-50 store content on inbox events"
```

---

## Task 3: Capture the question payload in the reducer

**Files:**
- Modify: `src/vibing_api/core/reducer.py`
- Test: `tests/api/test_reducer.py`

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_reducer.py`, add a pure-layer test near `test_reduce_agent_asked_question` (line ~87):

```python
def test_reduce_agent_asked_question_captures_content() -> None:
    updates = reduce(
        _event("agent_asked_question", payload={"question": "Redis or in-memory?"})
    )
    assert updates.inbox_event_type == "question"
    assert updates.inbox_content == "Redis or in-memory?"


def test_reduce_agent_asked_question_without_payload_has_no_content() -> None:
    assert reduce(_event("agent_asked_question")).inbox_content is None
```

And a persistence test near `test_agent_asked_question_creates_inbox` (line ~299):

```python
def test_agent_asked_question_persists_content(
    conn: sqlite3.Connection, seeded: tuple[str, str]
) -> None:
    dc_id, session_id = seeded
    project(
        RuntimeEvent(
            event_type="agent_asked_question",
            source=_SOURCE,
            devcontainer_id=dc_id,
            agent_session_id=session_id,
            payload={"question": "Redis or in-memory?"},
        ),
        conn,
    )
    row = conn.execute(
        "SELECT content FROM inbox_events WHERE agent_session_id = ?",
        (session_id,),
    ).fetchone()
    assert row[0] == "Redis or in-memory?"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_reducer.py::test_reduce_agent_asked_question_captures_content -v`
Expected: FAIL — `ProjectionUpdates` has no attribute `inbox_content`.

- [ ] **Step 3: Implement**

In `src/vibing_api/core/reducer.py`:

Add a field to `ProjectionUpdates` (after `inbox_event_type`):

```python
@dataclass(frozen=True)
class ProjectionUpdates:
    devcontainer_status: DevcontainerStatus | None = None
    session_status: AgentSessionStatus | None = None
    create_approval: bool = False
    requested_action: str = ""
    resolve_approval: ApprovalStatus | None = None
    resolve_approval_id: str | None = None
    inbox_event_type: InboxEventType | None = None
    inbox_content: str | None = None
    resolve_linked_inbox: bool = False
    resolve_inbox_event_id: str | None = None
    final_status: AgentSessionStatus | None = None
```

Update the `AGENT_ASKED_QUESTION` branch in `reduce()`:

```python
    if event_type == EventType.AGENT_ASKED_QUESTION:
        return ProjectionUpdates(
            inbox_event_type=inbox_event_type,
            inbox_content=payload.get("question"),
        )
```

In `project()`, pass `content` into the `inbox.create(...)` call:

```python
    if updates.inbox_event_type is not None and event.devcontainer_id is not None:
        inbox.create(
            devcontainer_id=event.devcontainer_id,
            event_type=updates.inbox_event_type,
            status="unread",
            agent_session_id=event.agent_session_id,
            approval_request_id=created_approval_id,
            content=updates.inbox_content,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_reducer.py -q`
Expected: PASS (new + existing reducer tests).

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/core/reducer.py tests/api/test_reducer.py
git commit -m "VIB-50 capture question content in reducer"
```

---

## Task 4: Expose `content` on the inbox detail API

**Files:**
- Modify: `src/vibing_api/api/schemas/inbox.py`
- Test: `tests/api/test_inbox_approvals.py`

- [ ] **Step 1: Write the failing test**

In `tests/api/test_inbox_approvals.py`, first extend the `_seed_inbox` helper to accept content:

```python
def _seed_inbox(
    dc_id: str,
    event_type: InboxEventType = "question",
    status: str = "unread",
    agent_session_id: str | None = None,
    content: str | None = None,
) -> str:
    with get_connection() as conn:
        event = InboxRepository(conn).create(
            dc_id, event_type, status, agent_session_id=agent_session_id, content=content
        )
        conn.commit()
    return event.id
```

Then add a detail test near `test_get_inbox_event_detail` (line ~238):

```python
def test_get_inbox_event_detail_includes_content(client: TestClient) -> None:
    dc_id = _create_dc(client)
    event_id = _seed_inbox(dc_id, "question", "unread", content="Redis or in-memory?")
    resp = client.get(f"/api/v1/inbox-events/{event_id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "Redis or in-memory?"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_inbox_approvals.py::test_get_inbox_event_detail_includes_content -v`
Expected: FAIL — `KeyError: 'content'` (field absent from the response).

- [ ] **Step 3: Implement**

In `src/vibing_api/api/schemas/inbox.py`, add `content` to `InboxEventDetail` only:

```python
class InboxEventDetail(InboxEvent):
    content: str | None
    devcontainer: Devcontainer
    agent_session: AgentSession | None
    approval_request: ApprovalRequest | None
```

> The detail route builds this via `InboxEventDetail(**vars(event), ...)`; `content` is already on the `event` dataclass (Task 2), so it flows through. The list schema (`InboxEvent`) is intentionally left unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_inbox_approvals.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_api/api/schemas/inbox.py tests/api/test_inbox_approvals.py
git commit -m "VIB-50 expose content on inbox detail API"
```

---

## Task 5: Seed sample question content

**Files:**
- Modify: `src/vibing_api/dev/sample_data.py`

- [ ] **Step 1: Add content to the sample question event**

In `src/vibing_api/dev/sample_data.py`, the `sample-ie-001` question entry (event_type `"question"`) — add a `content` key:

```python
    {
        "id": "sample-ie-001",
        "devcontainer_id": "sample-dc-api",
        "agent_session_id": "sample-as-api",
        "approval_request_id": None,
        "event_type": "question",
        "status": "unread",
        "content": "Which database should I use for the cache layer — Redis or in-memory?",
        "created_at": FIXED_TS,
        "updated_at": FIXED_TS,
    },
```

- [ ] **Step 2: Verify the insert path accepts the key**

No other change is needed: `seed()` builds each row's INSERT column list dynamically from `row.keys()`, so the new `content` key is inserted automatically. Other inbox rows without the key are unaffected (each row builds its own column list).

Run: `uv run python -c "from vibing_api.dev.sample_data import SAMPLE_INBOX_EVENTS; print('content' in SAMPLE_INBOX_EVENTS[0])"`
Expected: prints `True`.

- [ ] **Step 3: Run the suite**

Run: `uv run pytest tests/api -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS / no errors.

- [ ] **Step 4: Commit**

```bash
git add src/vibing_api/dev/sample_data.py
git commit -m "VIB-50 seed sample question content"
```

---

## Task 6: Add `content` to the frontend `InboxEventDetail` type

**Files:**
- Modify: `apps/web/src/lib/api/types.ts`

- [ ] **Step 1: Add the field**

In `apps/web/src/lib/api/types.ts`, update `InboxEventDetail`:

```typescript
export interface InboxEventDetail extends InboxEvent {
  content: string | null
  devcontainer: Devcontainer
  agent_session: AgentSession | null
  approval_request: ApprovalRequest | null
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd apps/web && pnpm exec tsc --noEmit`
Expected: PASS (no type errors).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/api/types.ts
git commit -m "VIB-50 add content to InboxEventDetail type"
```

---

## Task 7: Shared intervention state-machine hook

**Files:**
- Create: `apps/web/src/lib/intervention/useInterventionAction.ts`
- Test: `apps/web/src/lib/intervention/__tests__/useInterventionAction.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/lib/intervention/__tests__/useInterventionAction.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useInterventionAction } from '../useInterventionAction'
import { ApiError } from '../../api'

describe('useInterventionAction', () => {
  it('runs idle → submitting → awaiting on success', async () => {
    const { result } = renderHook(() => useInterventionAction('STALE_CODE'))
    expect(result.current.state.kind).toBe('idle')

    let resolve!: () => void
    const submit = () => new Promise<void>((r) => (resolve = r))
    act(() => {
      void result.current.run('go', submit)
    })
    expect(result.current.state).toEqual({ kind: 'submitting', tag: 'go' })

    await act(async () => {
      resolve()
    })
    expect(result.current.state.kind).toBe('awaiting')
  })

  it('maps the stale code to a stale state', async () => {
    const { result } = renderHook(() => useInterventionAction('STALE_CODE'))
    act(() => {
      void result.current.run('go', () => Promise.reject(new ApiError(409, 'STALE_CODE', 'x')))
    })
    await waitFor(() => expect(result.current.state.kind).toBe('stale'))
  })

  it('maps other errors to an error state', async () => {
    const { result } = renderHook(() => useInterventionAction('STALE_CODE'))
    act(() => {
      void result.current.run('go', () => Promise.reject(new Error('boom')))
    })
    await waitFor(() => expect(result.current.state.kind).toBe('error'))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm test -- useInterventionAction`
Expected: FAIL — cannot resolve `../useInterventionAction`.

- [ ] **Step 3: Implement**

Create `apps/web/src/lib/intervention/useInterventionAction.ts`:

```typescript
import { useState } from 'react'
import { ApiError } from '../api'

export type ActionState =
  | { kind: 'idle' }
  | { kind: 'submitting'; tag: string }
  | { kind: 'awaiting' }
  | { kind: 'stale' }
  | { kind: 'error'; message: string }

/** Owns the idle→submitting→awaiting/stale/error machine shared by approval and answer controls. */
export function useInterventionAction(staleCode: string) {
  const [state, setState] = useState<ActionState>({ kind: 'idle' })

  async function run(tag: string, submit: () => Promise<unknown>) {
    setState({ kind: 'submitting', tag })
    try {
      await submit()
      setState({ kind: 'awaiting' })
    } catch (err) {
      setState(
        err instanceof ApiError && err.code === staleCode
          ? { kind: 'stale' }
          : { kind: 'error', message: "Couldn't submit — try again." },
      )
    }
  }

  return { state, run }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && pnpm test -- useInterventionAction`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/intervention/useInterventionAction.ts apps/web/src/lib/intervention/__tests__/useInterventionAction.test.ts
git commit -m "VIB-50 add shared intervention action hook"
```

---

## Task 8: Shared `ActionButton` and `StatusNote` + barrel

**Files:**
- Create: `apps/web/src/lib/intervention/ActionButton.tsx`
- Create: `apps/web/src/lib/intervention/StatusNote.tsx`
- Create: `apps/web/src/lib/intervention/index.ts`

- [ ] **Step 1: Create `ActionButton`**

Create `apps/web/src/lib/intervention/ActionButton.tsx` (moved verbatim from `Approvals.tsx`):

```tsx
import { cn } from '../cn'

export function ActionButton({
  label,
  onClick,
  disabled,
  variant,
}: {
  label: string
  onClick: () => void
  disabled: boolean
  variant: 'approve' | 'reject'
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-md px-3 py-1 text-[12px] font-semibold disabled:opacity-40',
        variant === 'approve' ? 'bg-ok text-white' : 'border border-bad text-bad',
      )}
    >
      {label}
    </button>
  )
}
```

- [ ] **Step 2: Create `StatusNote`**

Create `apps/web/src/lib/intervention/StatusNote.tsx`:

```tsx
import type { ActionState } from './useInterventionAction'

/** Renders the awaiting/stale/error line beneath intervention controls. Copy is caller-supplied. */
export function StatusNote({
  state,
  awaitingNote,
  staleNote,
}: {
  state: ActionState
  awaitingNote: string
  staleNote: string
}) {
  if (state.kind === 'awaiting') return <div className="mt-1 text-[11px] text-accent">{awaitingNote}</div>
  if (state.kind === 'stale') return <div className="mt-1 text-[11px] text-bad">{staleNote}</div>
  if (state.kind === 'error') return <div className="mt-1 text-[11px] text-bad">{state.message}</div>
  return null
}
```

- [ ] **Step 3: Create the barrel**

Create `apps/web/src/lib/intervention/index.ts`:

```typescript
export { useInterventionAction, type ActionState } from './useInterventionAction'
export { ActionButton } from './ActionButton'
export { StatusNote } from './StatusNote'
```

- [ ] **Step 4: Verify it type-checks**

Run: `cd apps/web && pnpm exec tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/intervention/
git commit -m "VIB-50 add shared intervention button and status note"
```

---

## Task 9: Refactor `Approvals.tsx` onto the shared module

**Files:**
- Modify: `apps/web/src/routes/Approvals.tsx`
- Test: `apps/web/src/routes/__tests__/Approvals.test.tsx` (must stay green)

- [ ] **Step 1: Run the existing Approvals tests (baseline green)**

Run: `cd apps/web && pnpm test -- Approvals`
Expected: PASS. This is the regression guard for the refactor.

- [ ] **Step 2: Replace the inline machine with the shared module**

In `apps/web/src/routes/Approvals.tsx`:

Remove the local `type ActionState` block and the local `ActionButton` component. Add the import:

```typescript
import { useInterventionAction, ActionButton, StatusNote } from '../lib/intervention'
```

Rewrite `ApprovalRow` to use the hook:

```tsx
function ApprovalRow({ request }: { request: ApprovalRequest }) {
  const { state, run } = useInterventionAction('APPROVAL_REQUEST_NOT_PENDING')

  const resolve = (resolution: ApprovalResolution) =>
    run(resolution, () =>
      resolveAgentSessionApproval(request.devcontainer_id, request.agent_session_id, {
        approval_request_id: request.id,
        resolution,
      }),
    )

  const submitting = state.kind === 'submitting'
  const showActions =
    request.status === 'pending' && state.kind !== 'awaiting' && state.kind !== 'stale'

  return (
    <div className="flex items-center gap-3 border-b border-border px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="truncate font-mono text-[12.5px] font-semibold text-text">{request.requested_action}</div>
        <div className="mt-0.5 text-[11px] text-text-muted">
          {request.devcontainer_id} · session {request.agent_session_id.slice(0, 8)} ·{' '}
          {formatRelativeTime(request.created_at)}
          {state.kind === 'awaiting' && <span className="text-accent"> · submitted · awaiting runtime</span>}
        </div>
        <StatusNote
          state={state}
          awaitingNote=""
          staleNote="Already resolved elsewhere — no longer pending."
        />
      </div>
      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', badgeClass(request.status))}>
        {request.status}
      </span>
      {showActions && (
        <div className="flex shrink-0 gap-2">
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
    </div>
  )
}
```

> The Approvals row keeps its inline "· submitted · awaiting runtime" text in the meta line, so `StatusNote`'s `awaitingNote` is empty here (it renders nothing for awaiting when empty — adjust `StatusNote` to treat an empty string as "render nothing": change its awaiting branch to `if (state.kind === 'awaiting' && awaitingNote) return ...`). Apply that guard in `StatusNote.tsx`.

Apply the guard in `apps/web/src/lib/intervention/StatusNote.tsx`:

```tsx
  if (state.kind === 'awaiting') return awaitingNote ? <div className="mt-1 text-[11px] text-accent">{awaitingNote}</div> : null
```

- [ ] **Step 3: Run Approvals tests + type-check**

Run: `cd apps/web && pnpm test -- Approvals && pnpm exec tsc --noEmit`
Expected: PASS — behavior unchanged.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/routes/Approvals.tsx apps/web/src/lib/intervention/StatusNote.tsx
git commit -m "VIB-50 refactor Approvals onto shared intervention module"
```

---

## Task 10: Conversational Inbox detail panel with controls

**Files:**
- Modify: `apps/web/src/routes/Inbox.tsx`

- [ ] **Step 1: Add imports and a shared meta-line + bubble**

In `apps/web/src/routes/Inbox.tsx`, extend the API import to include the action endpoints and add the intervention import:

```typescript
import {
  listInboxEvents,
  fetchInboxEvent,
  sendAgentSessionUserInput,
  resolveAgentSessionApproval,
  useApiQuery,
  ApiError,
  type InboxEvent,
  type InboxEventDetail,
  type QueryState,
} from '../lib/api'
import { useInterventionAction, ActionButton, StatusNote } from '../lib/intervention'
```

> Do not add a new React import — the file already has `import { useEffect, useState } from 'react'` at the top, which covers the `useState` used by `AnswerControls`.

- [ ] **Step 2: Add an `ApprovalControls` sub-component**

Add to `Inbox.tsx`:

```tsx
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
```

- [ ] **Step 3: Add an `AnswerControls` sub-component**

Add to `Inbox.tsx`:

```tsx
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
```

- [ ] **Step 4: Rewrite `InboxDetail` to the conversational layout**

Replace the existing `InboxDetail` (and its `DetailRow` usage for question/approval) with:

```tsx
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

function InboxDetail({ detail, onClose }: { detail: InboxEventDetail; onClose: () => void }) {
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
        <div className="mx-4 rounded-md border border-border">
          <DetailRow label="Status">{detail.status}</DetailRow>
          <DetailRow label="Devcontainer">{detail.devcontainer.name}</DetailRow>
          <DetailRow label="Agent session">
            {detail.agent_session ? `${detail.agent_session.id.slice(0, 8)} · ${detail.agent_session.status}` : '—'}
          </DetailRow>
          <DetailRow label="Created">{formatRelativeTime(detail.created_at)}</DetailRow>
        </div>
      )}
    </div>
  )
}
```

> Keep the existing `DetailRow`, `typeBadgeClass`, `TYPE_LABEL`, `InboxDetailPanel`, and SSE registrations unchanged. `InboxDetailPanel` already registers `inbox`/`approvals`/`agent_sessions` invalidations and refetches — that drives the resolved state after a `202`.

- [ ] **Step 5: Type-check and lint**

Run: `cd apps/web && pnpm exec tsc --noEmit && pnpm exec eslint src`
Expected: PASS (no unused `DetailRow`/import errors; if `DetailRow` is now only used in the completion/failure branch that's fine).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/routes/Inbox.tsx
git commit -m "VIB-50 add intervention controls to inbox detail panel"
```

---

## Task 11: Inbox route tests for all states

**Files:**
- Modify: `apps/web/src/routes/__tests__/Inbox.test.tsx`

- [ ] **Step 1: Add an approval sample detail and helpers**

In `apps/web/src/routes/__tests__/Inbox.test.tsx`, add the action endpoints to the mock and a helper to build an approval detail. Update the top imports:

```typescript
import { listInboxEvents, fetchInboxEvent, sendAgentSessionUserInput, resolveAgentSessionApproval, ApiError } from '../../lib/api'
```

After the existing `vi.mocked` lines add:

```typescript
const mockSend = vi.mocked(sendAgentSessionUserInput)
const mockResolve = vi.mocked(resolveAgentSessionApproval)
```

After `sampleDetail`, add:

```typescript
const approvalDetail: InboxEventDetail = {
  ...ev({ id: 'ie2', event_type: 'approval_request', approval_request_id: 'ar1' }),
  content: null,
  devcontainer: sampleDetail.devcontainer,
  agent_session: sampleDetail.agent_session,
  approval_request: {
    id: 'ar1',
    devcontainer_id: 'dc1',
    agent_session_id: 'as1',
    status: 'pending',
    requested_action: 'run: pnpm migrate',
    created_at: new Date().toISOString(),
    decided_at: null,
  },
}
```

> Also add `content: 'Redis or in-memory?'` to the `sampleDetail` object literal so the question bubble renders real text.

- [ ] **Step 2: Write the state tests**

Add a new describe block:

```typescript
describe('Inbox intervention actions', () => {
  it('answers a question and shows the awaiting note after 202', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    mockSend.mockResolvedValue(sampleDetail.agent_session!)
    renderPage('/inbox?selected=ie1')

    await screen.findByText('Redis or in-memory?')
    await userEvent.type(screen.getByPlaceholderText('Type your answer…'), 'Use Redis')
    await userEvent.click(screen.getByText('Send answer'))

    await waitFor(() => expect(mockSend).toHaveBeenCalledWith('dc1', 'as1', { inbox_event_id: 'ie1', text: 'Use Redis' }))
    await waitFor(() => expect(screen.getByText('✓ Answer sent · awaiting runtime…')).toBeTruthy())
  })

  it('disables the send button while the answer is in flight', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    mockSend.mockReturnValue(new Promise(() => {}))
    renderPage('/inbox?selected=ie1')

    await screen.findByText('Redis or in-memory?')
    await userEvent.type(screen.getByPlaceholderText('Type your answer…'), 'Use Redis')
    await userEvent.click(screen.getByText('Send answer'))
    await waitFor(() => expect((screen.getByText('Sending…') as HTMLButtonElement).disabled).toBe(true))
  })

  it('shows the stale note when the question is no longer actionable', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail.mockResolvedValue(sampleDetail)
    mockSend.mockRejectedValue(new ApiError(409, 'INBOX_EVENT_NOT_ACTIONABLE', 'gone'))
    renderPage('/inbox?selected=ie1')

    await screen.findByText('Redis or in-memory?')
    await userEvent.type(screen.getByPlaceholderText('Type your answer…'), 'Use Redis')
    await userEvent.click(screen.getByText('Send answer'))
    await waitFor(() => expect(screen.getByText('This question is no longer awaiting an answer.')).toBeTruthy())
  })

  it('approves an approval request and shows the awaiting note', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request' })] })
    mockDetail.mockResolvedValue(approvalDetail)
    mockResolve.mockResolvedValue(sampleDetail.agent_session!)
    renderPage('/inbox?selected=ie2')

    await screen.findByText('Claude wants to run: pnpm migrate')
    await userEvent.click(screen.getByText('Approve'))
    await waitFor(() => expect(mockResolve).toHaveBeenCalledWith('dc1', 'as1', { approval_request_id: 'ar1', resolution: 'approved' }))
    await waitFor(() => expect(screen.getByText('✓ Submitted · awaiting runtime…')).toBeTruthy())
  })

  it('rejects an approval request', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request' })] })
    mockDetail.mockResolvedValue(approvalDetail)
    mockResolve.mockResolvedValue(sampleDetail.agent_session!)
    renderPage('/inbox?selected=ie2')

    await screen.findByText('Claude wants to run: pnpm migrate')
    await userEvent.click(screen.getByText('Reject'))
    await waitFor(() => expect(mockResolve).toHaveBeenCalledWith('dc1', 'as1', { approval_request_id: 'ar1', resolution: 'rejected' }))
  })

  it('shows the stale note when the approval is no longer pending', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie2', event_type: 'approval_request' })] })
    mockDetail.mockResolvedValue(approvalDetail)
    mockResolve.mockRejectedValue(new ApiError(409, 'APPROVAL_REQUEST_NOT_PENDING', 'gone'))
    renderPage('/inbox?selected=ie2')

    await screen.findByText('Claude wants to run: pnpm migrate')
    await userEvent.click(screen.getByText('Approve'))
    await waitFor(() => expect(screen.getByText('Already resolved elsewhere — no longer pending.')).toBeTruthy())
  })

  it('hides controls and reflects resolved state after an invalidation refetch', async () => {
    mockList.mockResolvedValue({ items: [ev({ id: 'ie1' })] })
    mockDetail
      .mockResolvedValueOnce(sampleDetail)
      .mockResolvedValueOnce({ ...sampleDetail, status: 'resolved' })
    renderPage('/inbox?selected=ie1')
    await screen.findByPlaceholderText('Type your answer…')

    act(() => {
      const [es] = MockEventSource.instances
      es.simulateOpen()
      es.simulateEvent('invalidate', { event_type: 'invalidate', scope: 'inbox', ids: ['ie1'] })
    })

    await waitFor(() => expect(screen.queryByPlaceholderText('Type your answer…')).toBeNull())
  })
})
```

- [ ] **Step 3: Run the Inbox tests**

Run: `cd apps/web && pnpm test -- Inbox`
Expected: PASS. If the approval bubble assertion fails on exact text, align the `Bubble` copy in `Inbox.tsx` (`Claude wants to ${requested_action}`) with the test string.

- [ ] **Step 4: Full frontend gate**

Run: `cd apps/web && pnpm test && pnpm exec tsc --noEmit && pnpm exec eslint src`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/__tests__/Inbox.test.tsx
git commit -m "VIB-50 test inbox intervention action states"
```

---

## Task 12: Full verification

- [ ] **Step 1: Backend checks**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
Expected: all PASS.

- [ ] **Step 2: Frontend checks**

Run: `cd apps/web && pnpm test && pnpm build`
Expected: all PASS.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Recreate the dev DB (delete the sqlite file), reseed sample data, run the stack, open `/inbox`, select the sample question and approval events, and confirm: question shows its content + answer form; approval shows approve/reject; submitting disables controls; after 202 the awaiting note appears.

- [ ] **Step 4: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "VIB-50 verification fixups"
```

---

## Acceptance criteria coverage

- Question answer form → `user-input` with `inbox_event_id`: Task 10 (`AnswerControls`), Task 11.
- Approve/reject → `approval-resolution` with `approval_request_id`: Task 10 (`ApprovalControls`), Task 11.
- Controls disabled while in flight: Task 10 (`disabled={submitting}`), Task 11.
- `202` shows accepted/pending immediately: Task 7 (`awaiting`), Task 10 (`StatusNote`), Task 11.
- Refetch on `inbox`/`approvals`/`agent_sessions` invalidations: existing `InboxDetailPanel` registrations (unchanged), Task 11 invalidation test.
- Resolved state without refresh: Task 10 (`resolved` hides controls), Task 11 invalidation test.
- Stale target errors displayed: Task 7 (`stale`), Task 10 (`staleNote`), Task 11 (both 409 codes).
- Route tests for all states: Task 11.
- Question prompt visible (design decision): Tasks 1–6, 10.
