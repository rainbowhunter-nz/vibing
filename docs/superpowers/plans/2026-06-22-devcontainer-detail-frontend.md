# Devcontainer Detail View — Frontend & Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Depends on:** `2026-06-22-devcontainer-live-state-backend.md` (the API now returns `source`, computes live `status`, serves harness status with a `known` flag, and exposes `POST /{id}/inject-runtime`). The MSW mock changes here let the frontend be built/verified without the live backend.

**Goal:** Turn the devcontainer detail-view controls into icons, add Delete and Inject-Runtime buttons, keep the harness install spinner until completion, render `?` for unknown harness status, show `source`, and verify it all with Playwright against the extended MSW mock.

**Architecture:** Extend the existing API client/types, then the existing MSW mock (`src/mock/state/*`, `handlers.ts`) to cover the new endpoints and `known` flag. Refactor `DevcontainerDetail.tsx` controls into an icon row, drive the harness spinner off SSE-confirmed status, and add Playwright e2e specs that run against `vite` with `VITE_API_MOCKING=true`.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind 4, MSW 2, Vitest + Testing Library (unit), Playwright (e2e, new).

## Global Constraints

- API base path `/api/v1`; client uses relative paths (Vite proxy in dev, same-origin in prod).
- Reuse the existing inline-SVG icon style (see `Devcontainers.tsx` icons) — no new icon library.
- Mock handlers match `*/api/v1/...`; mutable state lives in `src/mock/state/*`; SSE invalidations via `emitInvalidation(scope)`.
- `DevcontainerStatus` union must match backend: `'starting' | 'running' | 'stopping' | 'stopped' | 'error'` (no `'created'`).
- Frontend checks: `npm run lint`, `npm run typecheck`, `npm run test` (in `apps/web`).

---

### Task 1: Types + endpoints for `source`, `known`, inject-runtime

**Files:**
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/lib/api/endpoints.ts`
- Test: `apps/web/src/lib/api/endpoints.test.ts` (create if absent; else add cases)

**Interfaces:**
- Produces:
  ```ts
  type DevcontainerStatus = 'starting' | 'running' | 'stopping' | 'stopped' | 'error'
  type DevcontainerSource = 'manual' | 'discovered'
  interface Devcontainer { id; name; local_path; status; source; created_at: string | null; updated_at: string | null }
  interface HarnessStatusList { items: HarnessStatus[]; known: boolean }
  function injectRuntime(id: string): Promise<void>
  ```

- [ ] **Step 1: Write the failing test**

```ts
// apps/web/src/lib/api/endpoints.test.ts
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { injectRuntime } from './endpoints'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('injectRuntime', () => {
  it('POSTs to inject-runtime', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(null, { status: 202 }))
    await injectRuntime('dc-1')
    expect(spy).toHaveBeenCalledWith(
      '/api/v1/devcontainers/dc-1/inject-runtime',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm run test -- endpoints`
Expected: FAIL — `injectRuntime` not exported

- [ ] **Step 3: Implement**

In `apps/web/src/lib/api/types.ts`:
```ts
export type DevcontainerStatus = 'starting' | 'running' | 'stopping' | 'stopped' | 'error'
export type DevcontainerSource = 'manual' | 'discovered'

export interface Devcontainer {
  id: string
  name: string
  local_path: string
  status: DevcontainerStatus
  source: DevcontainerSource
  created_at: string | null
  updated_at: string | null
}

export interface HarnessStatusList {
  items: HarnessStatus[]
  known: boolean
}
```
(Leave `DevcontainerView extends Devcontainer`, `RuntimeConnection`, `HarnessStatus` as-is. Remove `status` from `DevcontainerUpdateBody`.)

In `apps/web/src/lib/api/endpoints.ts` add:
```ts
export function injectRuntime(id: string): Promise<void> {
  return sendJson<void>(`/devcontainers/${encodeURIComponent(id)}/inject-runtime`, 'POST')
}
```
(Match the existing `sendJson` signature used by `startDevcontainer`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm run test -- endpoints`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/lib/api/endpoints.ts apps/web/src/lib/api/endpoints.test.ts
git commit -m "feat(web): add source/known types and injectRuntime endpoint"
```

---

### Task 2: Extend MSW mock — source, discovered seeds, inject handler, harness `known`

**Files:**
- Modify: `apps/web/src/mock/state/seeds.ts`
- Modify: `apps/web/src/mock/state/devcontainers.ts`
- Modify: `apps/web/src/mock/state/harnesses.ts`
- Modify: `apps/web/src/mock/handlers.ts`

**Interfaces:**
- Produces: seeds include a `source` per devcontainer and at least one `discovered` entry; one devcontainer has **no** harness cache (→ `known:false`); `listHarnesses` returns `{ items, known }`; handlers serve `POST /devcontainers/:id/inject-runtime` (202) and `DELETE` honoring manual-vs-discovered (discovered stays, status resets to `stopped`).

- [ ] **Step 1: Update seeds**

In `apps/web/src/mock/state/seeds.ts`, add `source` + nullable timestamps to each `seedDevcontainers` entry and add a discovered one; mark one devcontainer as runtime-disconnected with no harness entry:
```ts
export const seedDevcontainers: Devcontainer[] = [
  { id: 'dc-seed-0001', name: 'my-webapp', local_path: '/home/dev/my-webapp', status: 'running', source: 'manual', created_at: '2024-01-10T08:00:00.000Z', updated_at: '2024-01-15T10:00:00.000Z' },
  { id: 'dc-seed-0002', name: 'api-svc', local_path: '/home/dev/api-svc', status: 'stopped', source: 'manual', created_at: '2024-01-11T08:00:00.000Z', updated_at: '2024-01-12T10:00:00.000Z' },
  { id: 'dc-seed-0003', name: 'docs-site', local_path: '/srv/devcontainers/docs-site', status: 'stopped', source: 'discovered', created_at: null, updated_at: null },
]

// dc-seed-0002 intentionally has NO harness entry → known:false → '?'
export const seedHarnesses: Record<string, HarnessStatus[]> = {
  'dc-seed-0001': [
    { name: 'claude-code', installed: true, authenticated: true },
    { name: 'codex', installed: true, authenticated: false },
    { name: 'cursor', installed: false, authenticated: false },
  ],
  'dc-seed-0003': [
    { name: 'claude-code', installed: false, authenticated: false },
  ],
}
```

- [ ] **Step 2: Update harness state to expose `known`**

In `apps/web/src/mock/state/harnesses.ts`:
```ts
export function listHarnesses(devcontainerId: string): HarnessStatusList {
  const items = store[devcontainerId]
  return items ? { items: clone(items), known: true } : { items: [], known: false }
}
```
(Add `installHarness`/`authenticateHarness` that create the entry if missing, matching existing behavior — flipping `installed`/`authenticated` true.)

- [ ] **Step 3: Update devcontainer state for source-aware delete + inject**

In `apps/web/src/mock/state/devcontainers.ts`:
```ts
export function deleteDevcontainer(id: string): void {
  const dc = store.find((d) => d.id === id)
  if (!dc) throw new NotFoundError(id)
  if (dc.source === 'discovered') {
    dc.status = 'stopped' // container removed, folder remains → reappears stopped
    return
  }
  store = store.filter((d) => d.id !== id)
}

export function injectRuntime(id: string): void {
  const dc = store.find((d) => d.id === id)
  if (!dc) throw new NotFoundError(id)
  // mock: mark runtime connected so harness panel becomes "known"
}
```
Adjust `createDevcontainer` to set `source: 'manual'`, `created_at`/`updated_at` to a fixed ISO string.

- [ ] **Step 4: Add handlers**

In `apps/web/src/mock/handlers.ts`, add inside the mutable-state handler list:
```ts
http.post('*/api/v1/devcontainers/:id/inject-runtime', ({ params }) => {
  dc.injectRuntime(String(params.id))
  emitInvalidation('runtime')
  emitInvalidation('harnesses')
  return new HttpResponse(null, { status: 202 })
}),
```
Confirm `GET /devcontainers/:id/harnesses` returns `hn.listHarnesses(id)` (now `{items, known}`) and `DELETE` calls `dc.deleteDevcontainer(id)` then `emitInvalidation('devcontainers')`.

- [ ] **Step 5: Verify mock compiles + unit tests pass**

Run: `cd apps/web && npm run typecheck && npm run test`
Expected: PASS (type errors from the new fields surface here — fix them).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/mock
git commit -m "feat(web): extend mock for source, discovered, inject-runtime, harness known"
```

---

### Task 3: Icon control row on detail view (Start/Stop/Inject/Delete)

**Files:**
- Modify: `apps/web/src/routes/DevcontainerDetail.tsx`
- Create: `apps/web/src/components/icons.tsx` (shared inline SVGs extracted from `Devcontainers.tsx`)
- Test: `apps/web/src/routes/DevcontainerDetail.test.tsx` (create)

**Interfaces:**
- Produces: a `LifecycleHeader` whose actions are icon buttons: Start (play, when not running), Stop (stop, when running), Inject-Runtime (always when running), Delete (trash, with confirm). Each shows a spinner while its action is pending. Source badge shown next to status.

- [ ] **Step 1: Extract shared icons**

Create `apps/web/src/components/icons.tsx` exporting `PlayIcon`, `StopIcon`, `TrashIcon`, `SpinnerIcon`, and a new `InjectIcon` (a downward-into-box / chip glyph). Copy the exact SVG markup from `Devcontainers.tsx` (lines for play/stop/trash/spinner) into named components, e.g.:
```tsx
export const PlayIcon = () => (
  <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden>
    <path d="M4 3.5v9l7-4.5-7-4.5Z" />
  </svg>
)
export const InjectIcon = () => (
  <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
    <path d="M8 2v7M5 6l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
    <rect x="3" y="11" width="10" height="3" rx="1" />
  </svg>
)
```
(Use the actual existing SVG paths for Play/Stop/Trash/Spinner from `Devcontainers.tsx`.) Then refactor `Devcontainers.tsx` to import from `icons.tsx` (no behavior change).

- [ ] **Step 2: Write the failing test**

```tsx
// apps/web/src/routes/DevcontainerDetail.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LifecycleHeader } from './DevcontainerDetail'

const base = {
  id: 'dc-1', name: 'demo', local_path: '/x', status: 'running' as const,
  source: 'manual' as const, created_at: null, updated_at: null,
  runtime: { runtime_connected: true },
}

describe('LifecycleHeader actions', () => {
  it('shows Stop, Inject, Delete when running', () => {
    render(<LifecycleHeader dc={base} busy={false} onAction={() => {}} />)
    expect(screen.getByTitle('Stop')).toBeInTheDocument()
    expect(screen.getByTitle('Inject runtime')).toBeInTheDocument()
    expect(screen.getByTitle('Delete')).toBeInTheDocument()
  })

  it('shows Start when stopped', () => {
    render(<LifecycleHeader dc={{ ...base, status: 'stopped' }} busy={false} onAction={() => {}} />)
    expect(screen.getByTitle('Start')).toBeInTheDocument()
  })
})
```
(`LifecycleHeader` must be exported and accept `{ dc, busy, onAction }`. If the current component embeds fetching, refactor it to a presentational header that takes an `onAction(kind: 'start'|'stop'|'inject'|'delete')` callback; the route wires the actual endpoint calls.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/web && npm run test -- DevcontainerDetail`
Expected: FAIL — titles not found / not exported

- [ ] **Step 4: Implement the icon header**

Refactor `LifecycleHeader` in `DevcontainerDetail.tsx` to render an icon button row. Each button uses `title` (for accessibility + the test) and shows `<SpinnerIcon/>` when that action is the pending one. Delete uses `window.confirm` before firing. Example shape:
```tsx
export function LifecycleHeader({ dc, busy, onAction }: HeaderProps) {
  const running = dc.status === 'running'
  return (
    <header className="flex items-center gap-3">
      <h1 className="text-lg font-medium">{dc.name}</h1>
      <StatusBadge status={dc.status} />
      <SourceBadge source={dc.source} />
      <span className={dotClass(dc.runtime.runtime_connected)} />
      <div className="ml-auto flex items-center gap-1">
        {running ? (
          <IconButton title="Stop" busy={busy} onClick={() => onAction('stop')}><StopIcon /></IconButton>
        ) : (
          <IconButton title="Start" busy={busy} onClick={() => onAction('start')}><PlayIcon /></IconButton>
        )}
        {running && (
          <IconButton title="Inject runtime" busy={busy} onClick={() => onAction('inject')}><InjectIcon /></IconButton>
        )}
        <IconButton title="Delete" danger busy={busy}
          onClick={() => { if (confirm(`Delete ${dc.name}?`)) onAction('delete') }}>
          <TrashIcon />
        </IconButton>
      </div>
    </header>
  )
}
```
Add `IconButton`, `StatusBadge`, `SourceBadge` (small local components; reuse list-view badge classes). In the route body, wire `onAction`:
```tsx
const act = async (kind: ActionKind) => {
  setBusy(true); setError(null)
  try {
    if (kind === 'start') await startDevcontainer(dc.id)
    else if (kind === 'stop') await stopDevcontainer(dc.id)
    else if (kind === 'inject') await injectRuntime(dc.id)
    else if (kind === 'delete') { await deleteDevcontainer(dc.id); navigate('/devcontainers'); return }
    refetch()
  } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  finally { setBusy(false) }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps/web && npm run test -- DevcontainerDetail`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/icons.tsx apps/web/src/routes/DevcontainerDetail.tsx apps/web/src/routes/Devcontainers.tsx apps/web/src/routes/DevcontainerDetail.test.tsx
git commit -m "feat(web): icon control row with start/stop/inject/delete on detail view"
```

---

### Task 4: Harness install spinner persists until SSE; `?` for unknown

**Files:**
- Modify: `apps/web/src/components/HarnessList.tsx`
- Modify: `apps/web/src/routes/DevcontainerDetail.tsx` (pass `known` through)
- Test: `apps/web/src/components/HarnessList.test.tsx` (create)

**Interfaces:**
- Produces: `HarnessList` accepts `{ devcontainerId, harnesses, known, onChange }`. When `known === false`, render a `?` row instead of the harness grid. The install/auth action keeps its spinner until the harness's `installed`/`authenticated` flips true in incoming props (SSE-driven), not when the POST resolves.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/HarnessList.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { HarnessList } from './HarnessList'

vi.mock('../lib/api/endpoints', () => ({
  installHarness: vi.fn().mockResolvedValue(undefined),
  authenticateHarness: vi.fn().mockResolvedValue(undefined),
}))

describe('HarnessList', () => {
  it('renders ? when status unknown', () => {
    render(<HarnessList devcontainerId="dc-1" harnesses={[]} known={false} onChange={() => {}} />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('keeps spinner after install click until prop flips installed', async () => {
    const h = [{ name: 'codex', installed: false, authenticated: false }]
    const { rerender } = render(
      <HarnessList devcontainerId="dc-1" harnesses={h} known onChange={() => {}} />,
    )
    fireEvent.click(screen.getByTitle('Install codex'))
    // still pending (POST resolved but SSE not yet) → spinner present
    expect(await screen.findByTestId('spinner-install-codex')).toBeInTheDocument()
    // SSE arrives → parent passes installed:true → spinner gone, check shown
    rerender(
      <HarnessList
        devcontainerId="dc-1"
        harnesses={[{ name: 'codex', installed: true, authenticated: false }]}
        known
        onChange={() => {}}
      />,
    )
    expect(screen.queryByTestId('spinner-install-codex')).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm run test -- HarnessList`
Expected: FAIL — `known` prop unused / spinner clears on POST

- [ ] **Step 3: Implement**

Refactor `HarnessList.tsx`:
- Add `known: boolean` prop. If `!known`, render a single muted row: `<div className="...">{harnesses.length === 0 ? '?' : '?'}</div>` — i.e. show `?` for both install and auth columns with a tooltip "Runtime disconnected — status unknown".
- Replace the `busy: string | null` single-shot pattern with a `pending: Set<string>` of keys (`install:codex`). On click, add the key and POST; **do not** remove it on resolve.
- Derive "show spinner" as `pending.has('install:'+name) && !h.installed`. When the prop flips `installed:true` (via SSE refetch), the spinner condition becomes false. Clear the stale key in a `useEffect` that prunes keys whose underlying flag is now satisfied.
- Give the spinner `data-testid={'spinner-install-' + name}` (and `spinner-auth-...`).

```tsx
const [pending, setPending] = useState<Set<string>>(new Set())

useEffect(() => {
  setPending((prev) => {
    const next = new Set(prev)
    for (const h of harnesses) {
      if (h.installed) next.delete('install:' + h.name)
      if (h.authenticated) next.delete('auth:' + h.name)
    }
    return next
  })
}, [harnesses])

const run = (key: string, fn: () => Promise<unknown>) => {
  setPending((p) => new Set(p).add(key))
  void fn().catch(() => setPending((p) => { const n = new Set(p); n.delete(key); return n }))
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm run test -- HarnessList`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/HarnessList.tsx apps/web/src/routes/DevcontainerDetail.tsx apps/web/src/components/HarnessList.test.tsx
git commit -m "feat(web): persist harness spinner until SSE; render ? when unknown"
```

---

### Task 5: Playwright setup

**Files:**
- Create: `apps/web/playwright.config.ts`
- Modify: `apps/web/package.json` (add `@playwright/test` dev dep + `e2e` script)
- Create: `apps/web/e2e/.gitkeep`

**Interfaces:** Playwright runs `vite` with mocking, base URL from the dev server.

- [ ] **Step 1: Add Playwright**

Run:
```bash
cd apps/web
npm install -D @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Add config**

```ts
// apps/web/playwright.config.ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://localhost:5173' },
  webServer: {
    command: 'npm run dev:mock',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})
```
Add to `package.json` scripts: `"e2e": "playwright test"`.

- [ ] **Step 3: Verify the harness starts**

Run: `cd apps/web && npx playwright test --list`
Expected: lists 0 tests (no specs yet) without error; confirms config loads.

- [ ] **Step 4: Commit**

```bash
git add apps/web/playwright.config.ts apps/web/package.json apps/web/package-lock.json apps/web/e2e/.gitkeep
git commit -m "chore(web): add Playwright e2e harness against mock dev server"
```

---

### Task 6: Playwright specs for the detail-view features

**Files:**
- Create: `apps/web/e2e/devcontainer-detail.spec.ts`

**Interfaces:** Drives the mock UI; asserts the new behaviors.

- [ ] **Step 1: Write the specs**

```ts
// apps/web/e2e/devcontainer-detail.spec.ts
import { expect, test } from '@playwright/test'

test('detail view shows icon controls for a running devcontainer', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0001')
  await expect(page.getByTitle('Stop')).toBeVisible()
  await expect(page.getByTitle('Inject runtime')).toBeVisible()
  await expect(page.getByTitle('Delete')).toBeVisible()
})

test('start button appears for a stopped devcontainer', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0002')
  await expect(page.getByTitle('Start')).toBeVisible()
})

test('unknown harness status renders ? when runtime disconnected', async ({ page }) => {
  // dc-seed-0002 has no harness cache in the mock → known:false
  await page.goto('/devcontainers/dc-seed-0002')
  await expect(page.getByText('?').first()).toBeVisible()
})

test('source is shown for a discovered devcontainer', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0003')
  await expect(page.getByText(/discovered/i)).toBeVisible()
})

test('delete navigates back to the list', async ({ page }) => {
  page.on('dialog', (d) => d.accept()) // confirm()
  await page.goto('/devcontainers/dc-seed-0002')
  await page.getByTitle('Delete').click()
  await expect(page).toHaveURL(/\/devcontainers\/?$/)
})

test('install spinner persists until status update', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0003') // codex not installed
  await page.getByTitle('Install claude-code').click()
  // mock emits harnesses invalidation → refetch flips installed → check appears
  await expect(page.getByTitle('Installed')).toBeVisible()
})
```
Adjust route paths/titles to the app's actual router (confirm the detail route is `/devcontainers/:id`). If the mock's install handler flips state synchronously, the spinner→check transition still exercises the SSE-driven refetch path.

- [ ] **Step 2: Run the specs**

Run: `cd apps/web && npm run e2e`
Expected: PASS (6 tests). Debug with `npm run e2e -- --headed` if a selector misses.

- [ ] **Step 3: Commit**

```bash
git add apps/web/e2e/devcontainer-detail.spec.ts
git commit -m "test(web): Playwright e2e for icon controls, ?, source, delete, spinner"
```

---

### Task 7: Frontend docs coherence

**Files:**
- Modify: `apps/web/CLAUDE.md` (if present; else the nearest frontend doc)
- Modify: root `README`/docs only if they describe devcontainer status persistence

- [ ] **Step 1: Update docs**

Note in the web CLAUDE.md: devcontainer `status` and harness status are now **live** (status union has no `created`); harness panel shows `?` when the runtime is disconnected (`known:false`); detail view uses icon controls incl. Inject-Runtime and Delete; Playwright e2e lives in `apps/web/e2e` and runs against `dev:mock` via `npm run e2e`.

- [ ] **Step 2: Final checks**

Run:
```bash
cd apps/web && npm run lint && npm run typecheck && npm run test && npm run e2e
```
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add apps/web/CLAUDE.md
git commit -m "docs(web): live status, harness unknown, icon controls, e2e"
```

---

## Self-Review

**Spec coverage:**
- Icon control buttons → Task 3 ✓
- Delete button (kills+removes via API; manual leaves list, discovered returns) → Tasks 2,3 ✓
- Inject-runtime button → Tasks 1,3 ✓
- Install spinner until done → Task 4 ✓
- `?` unknown harness status → Tasks 2,4 ✓
- Source label → Tasks 1,2,3 ✓
- Backend mock for UI → Task 2 (extends existing MSW) ✓
- Playwright verification → Tasks 5,6 ✓
- Docs coherence → Task 7 ✓

**Placeholder scan:** No TBDs. Two spots say "use the actual existing SVG paths" / "confirm the detail route" — these are explicit instructions to read one named source file, not deferred design.

**Type consistency:** `DevcontainerStatus` union matches backend (no `created`). `HarnessStatusList` gains `known: boolean` in both types and mock. `LifecycleHeader` props `{ dc, busy, onAction(kind) }` and `ActionKind = 'start'|'stop'|'inject'|'delete'` are used consistently in Task 3. `HarnessList` props `{ devcontainerId, harnesses, known, onChange }` consistent across Tasks 3–4 and tests.
