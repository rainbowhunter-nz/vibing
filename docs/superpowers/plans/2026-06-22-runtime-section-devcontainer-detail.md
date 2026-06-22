# Runtime Section on Devcontainer Detail — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the runtime status indicator and Inject-runtime control out of the devcontainer detail top bar into a dedicated "Runtime" section, with Inject greyed-out (disabled) when the container isn't running.

**Architecture:** Frontend-only change in `apps/web/src/routes/DevcontainerDetail.tsx`. The top `LifecycleHeader` keeps only lifecycle controls. A new `RuntimeSection` renders inside `ControlPanel` above "Coding harnesses", reusing the existing `act()` wiring (`{ dc, busy, onAction }`). `IconButton` gains a `disabled` prop, distinct from `busy`, so greyed (real icon, dimmed) reads differently from busy (spinner).

**Tech Stack:** React + TypeScript + Tailwind, Vitest + Testing Library, Playwright e2e.

## Global Constraints

- All backend access goes through `src/lib/api/` — no direct `fetch`. (No API change here; reuse existing `injectRuntime` via `act()`.)
- Compose classNames with `cn(...)`.
- Status copy: `Connected` / `Not connected`. Inject tooltip: `Inject runtime` (enabled) / `Start the container to inject runtime` (disabled).
- Runtime section sits **above** "Coding harnesses".
- Keep `apps/web/CLAUDE.md` coherent with the change.

---

### Task 1: Split `disabled` from `busy` on `IconButton`; remove runtime from `LifecycleHeader`

**Files:**
- Modify: `apps/web/src/routes/DevcontainerDetail.tsx` (`IconButton` ~54-85, `LifecycleHeader` ~89-147)
- Test: `apps/web/src/routes/DevcontainerDetail.test.tsx`

**Interfaces:**
- Produces: `IconButton` props `{ title: string; busy: boolean; disabled?: boolean; danger?: boolean; onClick: () => void; children: React.ReactNode }`. `busy` → spinner + non-interactive; `disabled` → real icon, dimmed, `onClick` not fired. `LifecycleHeader` no longer renders the runtime dot/label or the inject button.

- [ ] **Step 1: Update the LifecycleHeader test for the moved controls**

Replace the first test in `apps/web/src/routes/DevcontainerDetail.test.tsx` so the header no longer asserts Inject, and add an assertion that the runtime indicator/inject are gone:

```tsx
describe('LifecycleHeader actions', () => {
  it('shows Stop and Remove container when running, without runtime controls', () => {
    render(<LifecycleHeader dc={base} busy={false} onAction={() => {}} />)
    expect(screen.getByTitle('Stop')).toBeTruthy()
    expect(screen.getByTitle('Remove container')).toBeTruthy()
    expect(screen.queryByTitle('Inject runtime')).toBeNull()
    expect(screen.queryByText('Connected')).toBeNull()
  })

  it('shows Start when stopped', () => {
    render(<LifecycleHeader dc={{ ...base, status: 'stopped' }} busy={false} onAction={() => {}} />)
    expect(screen.getByTitle('Start')).toBeTruthy()
  })

  it('Start is disabled when status is starting', () => {
    render(<LifecycleHeader dc={{ ...base, status: 'starting' }} busy={false} onAction={() => {}} />)
    expect((screen.getByTitle('Start') as HTMLButtonElement).disabled).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/web && pnpm test -- DevcontainerDetail`
Expected: FAIL — `queryByTitle('Inject runtime')` still finds the header inject button.

- [ ] **Step 3: Add `disabled` support to `IconButton`**

Replace the `IconButton` component:

```tsx
function IconButton({
  title,
  busy,
  disabled,
  danger,
  onClick,
  children,
}: {
  title: string
  busy: boolean
  disabled?: boolean
  danger?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  const inactive = busy || disabled
  return (
    <button
      type="button"
      title={title}
      disabled={inactive}
      onClick={onClick}
      className={cn(
        'flex h-7 w-7 items-center justify-center rounded-[5px]',
        inactive
          ? 'cursor-not-allowed opacity-40'
          : danger
            ? 'cursor-pointer text-bad hover:bg-surface-muted'
            : 'cursor-pointer text-text-muted hover:bg-surface-muted',
      )}
    >
      {busy ? <SpinnerIcon /> : children}
    </button>
  )
}
```

- [ ] **Step 4: Remove the runtime indicator and inject button from `LifecycleHeader`**

Delete the runtime `<span>` block (the `inline-flex … runtime` indicator) and the `{running && (<IconButton title="Inject runtime" …/>)}` block. The action row becomes:

```tsx
        <div className="ml-auto flex items-center gap-1">
          {running ? (
            <IconButton title="Stop" busy={busy} onClick={() => onAction('stop')}>
              <StopIcon />
            </IconButton>
          ) : (
            <IconButton title="Start" busy={busy || transitioning} onClick={() => onAction('start')}>
              <PlayIcon />
            </IconButton>
          )}
          <IconButton
            title="Remove container"
            danger
            busy={busy}
            onClick={() => { if (!busy && confirm(`Remove the container for ${dc.name}? The devcontainer stays in the list.`)) onAction('remove') }}
          >
            <TrashIcon />
          </IconButton>
        </div>
```

Remove the now-unused `InjectIcon` import only if Task 2 won't reintroduce it in the same file — it will, so leave the import.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd apps/web && pnpm test -- DevcontainerDetail`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/routes/DevcontainerDetail.tsx apps/web/src/routes/DevcontainerDetail.test.tsx
git commit -m "refactor(web): drop runtime controls from devcontainer lifecycle header"
```

---

### Task 2: Add `RuntimeSection` and render it above Coding harnesses

**Files:**
- Modify: `apps/web/src/routes/DevcontainerDetail.tsx` (`ControlPanel` ~175-195, `DevcontainerDetail` render ~243-244)
- Test: `apps/web/src/routes/DevcontainerDetail.test.tsx`

**Interfaces:**
- Consumes: `IconButton` with `disabled` (Task 1); `act()` / `onAction(kind)` and `busy` from `DevcontainerDetail`; `SectionTitle`; `dc.runtime.runtime_connected`; `dc.status`.
- Produces: exported `RuntimeSection({ dc, busy, onAction }: { dc: DevcontainerView; busy: boolean; onAction: (kind: ActionKind) => void })`. `ControlPanel` gains `busy` and `onAction` props and renders `RuntimeSection` before the harness `<section>`.

- [ ] **Step 1: Write failing tests for `RuntimeSection`**

Add to `apps/web/src/routes/DevcontainerDetail.test.tsx` (extend the import on line 3 to include `RuntimeSection`):

```tsx
import { LifecycleHeader, RuntimeSection } from './DevcontainerDetail'
```

```tsx
describe('RuntimeSection', () => {
  it('shows Connected and an enabled Inject when running and connected', () => {
    const calls: string[] = []
    render(<RuntimeSection dc={base} busy={false} onAction={(k) => calls.push(k)} />)
    expect(screen.getByText('Connected')).toBeTruthy()
    const inject = screen.getByTitle('Inject runtime') as HTMLButtonElement
    expect(inject.disabled).toBe(false)
    inject.click()
    expect(calls).toEqual(['inject'])
  })

  it('shows Not connected and a disabled Inject when stopped', () => {
    const calls: string[] = []
    const dc = { ...base, status: 'stopped' as const, runtime: { runtime_connected: false } }
    render(<RuntimeSection dc={dc} busy={false} onAction={(k) => calls.push(k)} />)
    expect(screen.getByText('Not connected')).toBeTruthy()
    const inject = screen.getByTitle('Start the container to inject runtime') as HTMLButtonElement
    expect(inject.disabled).toBe(true)
    inject.click()
    expect(calls).toEqual([])
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/web && pnpm test -- DevcontainerDetail`
Expected: FAIL — `RuntimeSection` is not exported.

- [ ] **Step 3: Implement `RuntimeSection`**

Add above `ControlPanel` in `apps/web/src/routes/DevcontainerDetail.tsx`:

```tsx
export function RuntimeSection({
  dc,
  busy,
  onAction,
}: {
  dc: DevcontainerView
  busy: boolean
  onAction: (kind: ActionKind) => void
}) {
  const running = dc.status === 'running'
  const connected = dc.runtime.runtime_connected
  return (
    <section className="mb-5">
      <SectionTitle>Runtime</SectionTitle>
      <div className="flex items-center gap-2 text-[13px]">
        <span className={cn('h-2 w-2 rounded-full', connected ? 'bg-ok' : 'bg-text-subtle')} />
        <span className={connected ? 'text-text' : 'text-text-muted'}>
          {connected ? 'Connected' : 'Not connected'}
        </span>
        <div className="ml-auto">
          <IconButton
            title={running ? 'Inject runtime' : 'Start the container to inject runtime'}
            busy={busy && running}
            disabled={!running}
            onClick={() => onAction('inject')}
          >
            <InjectIcon />
          </IconButton>
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Thread props through `ControlPanel` and render the section**

Change `ControlPanel`'s signature and body:

```tsx
function ControlPanel({
  dc,
  busy,
  onAction,
}: {
  dc: DevcontainerView
  busy: boolean
  onAction: (kind: ActionKind) => void
}) {
  const { register } = useSseInvalidation()
  const { state: harnessState, refetch: refetchHarnesses } = useApiQuery(() => fetchHarnesses(dc.id), [dc.id])

  useEffect(() => register('harnesses', refetchHarnesses), [register, refetchHarnesses])

  return (
    <div className="p-4">
      <RuntimeSection dc={dc} busy={busy} onAction={onAction} />
      <section>
        <SectionTitle>Coding harnesses</SectionTitle>
        {harnessState.kind === 'ready' ? (
          <HarnessList devcontainerId={dc.id} harnesses={harnessState.data.items} known={harnessState.data.known} onChange={refetchHarnesses} />
        ) : harnessState.kind === 'error' ? (
          <ErrorState {...loadError('harnesses')} />
        ) : (
          <p className="text-[13px] text-text-muted">Loading harnesses…</p>
        )}
      </section>
    </div>
  )
}
```

Update the render site in `DevcontainerDetail`:

```tsx
            <LifecycleHeader dc={dc} busy={busy} onAction={(kind) => act(kind, dc)} />
            <ControlPanel dc={dc} busy={busy} onAction={(kind) => act(kind, dc)} />
```

- [ ] **Step 5: Run the full web test suite**

Run: `cd apps/web && pnpm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/routes/DevcontainerDetail.tsx apps/web/src/routes/DevcontainerDetail.test.tsx
git commit -m "feat(web): dedicated runtime section with disabled inject when stopped"
```

---

### Task 3: e2e for stopped Inject + docs coherence

**Files:**
- Modify: `apps/web/e2e/devcontainer-detail.spec.ts`
- Modify: `apps/web/CLAUDE.md`

**Interfaces:**
- Consumes: `RuntimeSection` rendering from Task 2. Seeds: `dc-seed-0001` running/connected, `dc-seed-0002` stopped/not-connected.

- [ ] **Step 1: Add an e2e test for the disabled Inject on a stopped devcontainer**

In `apps/web/e2e/devcontainer-detail.spec.ts`, after the "stopped devcontainer shows Start" test, add:

```ts
test('stopped devcontainer shows runtime as not connected with Inject disabled', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0002')
  await expect(page.getByText('Not connected')).toBeVisible()
  await expect(page.getByTitle('Start the container to inject runtime')).toBeDisabled()
})
```

The existing "running devcontainer shows … Inject …" test still passes — Inject keeps the title `Inject runtime` when running, just relocated.

- [ ] **Step 2: Run e2e**

Run: `cd apps/web && pnpm e2e`
Expected: PASS (all detail specs, including the new one).

- [ ] **Step 3: Update `apps/web/CLAUDE.md` detail-view description**

In the paragraph describing the detail view (line ~10), replace the icon-controls clause so it reflects the new structure. Change:

> The detail view uses icon controls (Start/Stop, plus Inject-Runtime when running, and Remove-container with confirm — …)

to:

> The detail view's top bar carries lifecycle icon controls (Start/Stop, and Remove-container with confirm — kills+removes the container via `removeContainer`/`POST .../remove-container` but keeps the devcontainer in the list, unlike the list page's trash which `DELETE`s the record). Runtime lives in its own "Runtime" section below (above Coding harnesses): a connected/not-connected indicator (`dc.runtime.runtime_connected`) plus an Inject-runtime icon button that is greyed/disabled unless the container is running.

Keep the rest of the sentence (the install/authenticate spinner clause) intact.

- [ ] **Step 4: Run lint/build to confirm coherence**

Run: `cd apps/web && pnpm build`
Expected: PASS (tsc + vite).

- [ ] **Step 5: Commit**

```bash
git add apps/web/e2e/devcontainer-detail.spec.ts apps/web/CLAUDE.md
git commit -m "test(web): e2e for disabled inject; docs for runtime section"
```

---

## Self-Review

**Spec coverage:**
- Remove runtime indicator + inject from top bar → Task 1, Step 4. ✓
- New Runtime section, status indicator, above harnesses → Task 2. ✓
- Inject greyed/disabled when not running, spinner only for in-flight inject → Task 2 (`disabled={!running}`, `busy={busy && running}`) + Task 1 `IconButton.disabled`. ✓
- Copy "Connected"/"Not connected" and tooltips → Task 2 + Global Constraints. ✓
- Tests (status, disabled-no-call, enabled-calls, header no longer has runtime) → Tasks 1-2. ✓
- e2e + CLAUDE.md coherence → Task 3. ✓

**Placeholder scan:** none — all steps carry full code/commands.

**Type consistency:** `ActionKind`, `DevcontainerView`, `IconButton` props, and `RuntimeSection`/`ControlPanel` signatures match across tasks. `onAction('inject')` matches the `act()` switch.
