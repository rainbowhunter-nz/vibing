# Runtime `error` State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface a failed inject (bootstrap install or preflight) as a distinct `error` runtime state in the indicator, retryable via the existing Inject button.

**Architecture:** Add a 4th `RuntimeState` value, `error`. `RuntimeService.inject()` sets it as a sticky transient on inject failure (instead of clearing to `disconnected`). The resolver maps the `error` transient to `ERROR` (connected still wins). Frontend adds a red dot + "Error" label; the Inject button already renders for every non-connected state, so retry → `launching` falls out for free.

**Tech Stack:** Python (FastAPI, pytest), React + TypeScript + Tailwind (vitest).

## Global Constraints

- `RuntimeState` union after this change: `connected | launching | disconnected | error` (backend `StrEnum`, frontend TS union must match exactly).
- `error` is set **only** on synchronous inject failure (`inject() == False`: bootstrap install **or** preflight). The launch **timeout** stays `disconnected` — do not change `_expire_launching`.
- `error` is sticky: cleared only by a retry inject (overwrites with `launching`), `stop-runtime`, or WS-connect. Do not add clearing on container stop/teardown.
- Connected wins over `error` in the resolver — a live runtime never shows `error`.
- No new DTO field — the reason lives in the runtime log (log-only surfacing). `RuntimeConnection.state` already carries `RuntimeState`, so `error` flows through unchanged.
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Python checks from repo root: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`. Frontend from `apps/web`: `pnpm test` (never npm).

---

### Task 1: Backend — `error` state in enum, resolver, and service

**Files:**
- Modify: `src/vibing_api/core/vocabularies.py` — add `ERROR` to `RuntimeState`.
- Modify: `src/vibing_api/core/runtime_status_resolver.py` — map `ERROR` transient.
- Modify: `src/vibing_api/core/runtime_service.py:44-48` — set `ERROR` on inject failure.
- Test: `tests/api/test_runtime_status_resolver.py`, `tests/api/test_runtime_service.py`.

**Interfaces:**
- Consumes: `RuntimeState` (`StrEnum`), `LiveStateStore.set_runtime_transient(id, state)` / `clear_runtime_transient(id)` / `get_runtime_transient(id)`, `resolve_runtime_state(transient: RuntimeState | None, connected: bool) -> RuntimeState`.
- Produces: `RuntimeState.ERROR` (string value `"error"`); `inject()` now leaves an `ERROR` transient on failure rather than no transient.

- [ ] **Step 1: Add the failing resolver tests**

Append to `tests/api/test_runtime_status_resolver.py`:

```python
def test_error_when_transient_error_and_not_connected() -> None:
    assert resolve_runtime_state(RuntimeState.ERROR, False) == RuntimeState.ERROR


def test_connected_wins_over_error() -> None:
    assert resolve_runtime_state(RuntimeState.ERROR, True) == RuntimeState.CONNECTED
```

- [ ] **Step 2: Run the resolver tests to verify they fail**

Run: `uv run pytest tests/api/test_runtime_status_resolver.py -q`
Expected: FAIL — `AttributeError: ERROR` (enum member does not exist yet).

- [ ] **Step 3: Add `ERROR` to the enum**

In `src/vibing_api/core/vocabularies.py`, extend `RuntimeState`:

```python
class RuntimeState(StrEnum):
    CONNECTED = auto()
    LAUNCHING = auto()
    DISCONNECTED = auto()
    ERROR = auto()
```

- [ ] **Step 4: Handle the `ERROR` transient in the resolver**

Replace the body of `resolve_runtime_state` in `src/vibing_api/core/runtime_status_resolver.py`:

```python
def resolve_runtime_state(transient: RuntimeState | None, connected: bool) -> RuntimeState:
    if connected:
        return RuntimeState.CONNECTED
    if transient == RuntimeState.LAUNCHING:
        return RuntimeState.LAUNCHING
    if transient == RuntimeState.ERROR:
        return RuntimeState.ERROR
    return RuntimeState.DISCONNECTED
```

- [ ] **Step 5: Run the resolver tests to verify they pass**

Run: `uv run pytest tests/api/test_runtime_status_resolver.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Update the service test for the failure path**

In `tests/api/test_runtime_service.py`, replace `test_inject_failure_clears_to_disconnected` with:

```python
def test_inject_failure_sets_error_transient() -> None:
    svc = _service(FakeInjector(inject_ok=False))
    asyncio.run(svc.inject("dc1", "/work/repo"))
    assert svc._live.get_runtime_transient("dc1") == RuntimeState.ERROR


def test_inject_retry_overwrites_error_with_launching() -> None:
    svc = _service(FakeInjector(inject_ok=True), timeout=999)
    svc._live.set_runtime_transient("dc1", RuntimeState.ERROR)
    asyncio.run(svc.inject("dc1", "/work/repo"))
    assert svc._live.get_runtime_transient("dc1") == RuntimeState.LAUNCHING
```

- [ ] **Step 7: Run the service tests to verify the failure-path test fails**

Run: `uv run pytest tests/api/test_runtime_service.py -q`
Expected: FAIL — `test_inject_failure_sets_error_transient` asserts `ERROR` but `inject()` still clears the transient (returns `None`).

- [ ] **Step 8: Set `ERROR` on inject failure**

In `src/vibing_api/core/runtime_service.py`, change the failure branch of `inject()` (currently `self._live.clear_runtime_transient(devcontainer_id)`):

```python
    async def inject(self, devcontainer_id: str, local_path: str) -> None:
        self._live.set_runtime_transient(devcontainer_id, RuntimeState.LAUNCHING)
        self._publish(devcontainer_id)
        launched = await self._injector.inject_by_path(devcontainer_id, local_path)
        if not launched:
            self._live.set_runtime_transient(devcontainer_id, RuntimeState.ERROR)
            self._publish(devcontainer_id)
            return
        run_in_background(self._expire_launching(devcontainer_id))
```

Leave `_expire_launching` and `stop` unchanged — both still clear the transient → `disconnected`.

- [ ] **Step 9: Run the full backend suite**

Run: `uv run pytest tests/api/test_runtime_service.py tests/api/test_runtime_status_resolver.py -q`
Expected: PASS. Then `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src` — all clean.

- [ ] **Step 10: Commit**

```bash
git add src/vibing_api/core/vocabularies.py src/vibing_api/core/runtime_status_resolver.py src/vibing_api/core/runtime_service.py tests/api/test_runtime_service.py tests/api/test_runtime_status_resolver.py
git commit -m "feat(api): runtime error state on inject failure

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Frontend — `error` indicator + mock

**Files:**
- Modify: `apps/web/src/lib/api/types.ts:32` — extend `RuntimeState` union.
- Modify: `apps/web/src/routes/DevcontainerDetail.tsx:171-175` (`RUNTIME_LABEL`) and `:217-223` (dot colour).
- Modify: `apps/web/src/mock/state/devcontainers.ts:7-10` — seed one devcontainer in `error`.
- Test: `apps/web/src/routes/DevcontainerDetail.test.tsx`.

**Interfaces:**
- Consumes: `RuntimeState.ERROR` from the backend (string `"error"`), surfaced as `dc.runtime.state === 'error'`.
- Produces: nothing downstream — terminal UI change.

- [ ] **Step 1: Add the failing frontend test**

Append inside the `describe('RuntimeSection', ...)` block in `apps/web/src/routes/DevcontainerDetail.test.tsx`:

```tsx
  it('shows Error and a visible Inject button when state is error and running', () => {
    const calls: string[] = []
    const dc = { ...base, status: 'running' as const, runtime: { state: 'error' as const } }
    render(<RuntimeSection dc={dc} busy={false} onAction={(k) => calls.push(k)} />)
    expect(screen.getByText('Error')).toBeTruthy()
    const inject = screen.getByTitle('Inject runtime') as HTMLButtonElement
    expect(inject.disabled).toBe(false)
    inject.click()
    expect(calls).toEqual(['inject'])
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `apps/web`): `pnpm test -- --run DevcontainerDetail`
Expected: FAIL — type error on `state: 'error'` (not in the union) and/or `getByText('Error')` finds nothing (`RUNTIME_LABEL` returns `undefined` → renders empty).

- [ ] **Step 3: Extend the `RuntimeState` union**

In `apps/web/src/lib/api/types.ts`, line 32:

```ts
export type RuntimeState = 'connected' | 'launching' | 'disconnected' | 'error'
```

- [ ] **Step 4: Add the `error` label and dot colour**

In `apps/web/src/routes/DevcontainerDetail.tsx`, add the label to `RUNTIME_LABEL`:

```tsx
const RUNTIME_LABEL: Record<string, string> = {
  connected: 'Connected',
  launching: 'Launching…',
  disconnected: 'Disconnected',
  error: 'Error',
}
```

Then, inside `RuntimeSection`, add the `error` derived flag and the red dot. Change the flags block (currently `const connected = ...` / `const launching = ...`):

```tsx
  const running = dc.status === 'running'
  const state = dc.runtime.state
  const connected = state === 'connected'
  const launching = state === 'launching'
  const error = state === 'error'
```

And the dot `className` (currently `connected ? 'bg-ok' : launching ? 'bg-accent' : 'bg-text-subtle'`):

```tsx
        <span
          className={cn(
            'h-2 w-2 rounded-full',
            connected ? 'bg-ok' : launching ? 'bg-accent' : error ? 'bg-bad' : 'bg-text-subtle',
          )}
        />
```

Leave the Inject/Stop control block unchanged — it already renders Inject for every non-connected state, enabled when the container is running.

- [ ] **Step 5: Run the frontend test to verify it passes**

Run (from `apps/web`): `pnpm test -- --run DevcontainerDetail`
Expected: PASS, including the existing RuntimeSection cases.

- [ ] **Step 6: Seed an `error` runtime in the mock for inspection**

In `apps/web/src/mock/state/devcontainers.ts`, set the second seed's runtime to `error` (currently `'dc-seed-0002': { state: 'disconnected' }`):

```ts
  'dc-seed-0002': { state: 'error' },
```

- [ ] **Step 7: Run the mock state tests and typecheck**

Run (from `apps/web`): `pnpm test -- --run` then `pnpm build`
Expected: PASS / build succeeds (tsc clean — the union now admits `'error'`).

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/routes/DevcontainerDetail.tsx apps/web/src/routes/DevcontainerDetail.test.tsx apps/web/src/mock/state/devcontainers.ts
git commit -m "feat(web): runtime error indicator (red dot, retry via Inject)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Docs coherence

**Files:**
- Modify: `docs/adr/0017-the-devcontainer-runtime-has-a-user-driven-control-plane-observed-lifecycle.md` — second amendment.
- Modify: `CONTEXT.md` — runtime-lifecycle resolved states.
- Modify: `src/vibing_api/CLAUDE.md` — `runtime_service.py` / `runtime_status_resolver.py` bullets.
- Modify: `apps/web/CLAUDE.md` — runtime indicator description.

**Interfaces:** none (documentation only).

- [ ] **Step 1: Amend ADR-0017**

In the ADR, immediately **before** the final `Status: accepted` line, add a second amendment paragraph:

```markdown
**Amendment (2026-06-23): a synchronous inject failure resolves to `error`, not `disconnected`.**
Refining the coarse-`disconnected` stance above: a failed inject (`inject() == False` — bootstrap
install **or** the preflight from the first amendment) now sets a **sticky `error` transient** so the
indicator distinguishes "tried to launch and the synchronous half failed" from a never-injected or
stopped runtime. This adds exactly **one** state — `error` — retryable via the existing Inject button
(which overwrites it with `launching`). The launch **timeout** (spawned but never connected) stays
`disconnected`, and the *reason* still lives in the log (no DTO field): `error` is a coarse signal,
not a message. Resolved runtime states are now `connected | launching | disconnected | error`.
```

- [ ] **Step 2: Update `CONTEXT.md` runtime lifecycle**

In `CONTEXT.md`, in the "### Runtime lifecycle" section, change the "Three resolved states" lead-in to four and add the `error` bullet after the `disconnected` bullet:

Change `The Devcontainer Runtime's state as the Control Plane observes it. Three resolved states:` to `… Four resolved states:`, and after the `disconnected` bullet add:

```markdown
- `error` — a synchronous inject failure (bootstrap install or preflight unreachable). A sticky
  `LiveStateStore` transient set when `inject()` returns failure; distinguishes a failed launch
  attempt from the `disconnected` catch-all. Cleared by a retry inject (→ `launching`), stop, or
  WS-connect. The reason is in the runtime log, not the state. A launch **timeout** stays
  `disconnected`.
```

- [ ] **Step 3: Update `src/vibing_api/CLAUDE.md`**

In `src/vibing_api/CLAUDE.md`:
- In the `core/live_state.py` bullet, change the runtime-state transient note from `(\`launching\`) cleared on WS connect / launch timeout` to `(\`launching\`, or sticky \`error\` on inject failure) cleared on WS connect / launch timeout / retry inject`.
- In the `core/runtime_service.py` bullet, append: ` On inject failure (bootstrap or preflight) it sets a sticky \`error\` transient (retry inject overwrites it with \`launching\`); the ~30s timeout still resolves to \`disconnected\`.`
- In the `core/runtime_status_resolver.py` bullet, change `connected (WS) wins, else \`launching\` transient, else \`disconnected\`` to `connected (WS) wins, else \`launching\` transient, else \`error\` transient, else \`disconnected\``.

- [ ] **Step 4: Update `apps/web/CLAUDE.md`**

In `apps/web/CLAUDE.md`, in the runtime indicator sentence, change `a three-state indicator (\`dc.runtime.state\` — \`connected\` green / \`launching\` accent / \`disconnected\` grey)` to `a four-state indicator (\`dc.runtime.state\` — \`connected\` green / \`launching\` accent / \`error\` red (a failed inject) / \`disconnected\` grey)`.

- [ ] **Step 5: Verify coherence and commit**

Run: `rg -n "Three resolved|three-state" CONTEXT.md apps/web/CLAUDE.md` — expect no matches (both updated).

```bash
git add docs/adr/0017-the-devcontainer-runtime-has-a-user-driven-control-plane-observed-lifecycle.md CONTEXT.md src/vibing_api/CLAUDE.md apps/web/CLAUDE.md
git commit -m "docs: runtime error state coherence (ADR-0017, CONTEXT, CLAUDE)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Enum `ERROR` → Task 1 Step 3. Resolver mapping → Task 1 Step 4. Service sets `error` on inject-fail → Task 1 Step 8. Retry → launching covered by the existing `inject()` setting `LAUNCHING` first (Task 1 test Step 6). Timeout stays disconnected → unchanged `_expire_launching` (constraint, no edit). Frontend union/label/dot → Task 2 Steps 3-4. Inject retry visible → Task 2 test Step 1 + unchanged control block. Mock inspectable → Task 2 Step 6. Logs-only (no DTO field) → no schema task, asserted by constraints. ADR/CONTEXT/CLAUDE coherence → Task 3. All spec sections covered.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; commands have expected output. Clean.

**Type consistency:** `RuntimeState.ERROR` (value `"error"`) used identically across vocabularies, resolver, service; frontend union `'error'` matches. `RUNTIME_LABEL.error = 'Error'` matches the test's `getByText('Error')`. Inject button title `'Inject runtime'` matches the Task 2 test selector (the running case). Consistent.
