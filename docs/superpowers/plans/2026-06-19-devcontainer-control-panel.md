# Devcontainer Runtime Control Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chat-based devcontainer detail page with a dark-themed runtime control panel: lifecycle header, coding-harness status list, and a delegated-runs viewer — all mock-backed.

**Architecture:** Frontend-only (mock-first). New REST endpoints are mocked via MSW + mutable in-browser state + scenarios; their contract is documented in the spec for later backend work. The whole app is re-themed to dark slate + green via centralized `index.css` `@theme` tokens. The obsolete chat/stream/agent-session frontend code is deleted.

**Tech Stack:** React 19 + Vite + TypeScript + Tailwind v4 + MSW. Tests: Vitest + @testing-library/react. Final verification: Playwright MCP browser tools.

## Global Constraints

- All backend access goes through `apps/web/src/lib/api/` — components never `fetch` directly. (apps/web/CLAUDE.md)
- New API call ⇒ add to `endpoints.ts` + `types.ts`, and update the mock layer in the same change (handlers, fixtures, mutable state, invalidation controls). (apps/web/CLAUDE.md)
- Compose classNames with `cn(...)`. (apps/web/CLAUDE.md)
- DTO types stay in sync with backend Pydantic schemas; harness fields are `name`/`installed`/`authenticated` (matches `HarnessStatus`); delegated-run statuses are `running`/`completed`/`failed`/`stopped` (matches `DelegatedRunManager._Run`).
- Theme is dark-only — no light/dark toggle.
- Run all commands from `apps/web/`. Checks: `pnpm test`, `pnpm build`.
- Keep `apps/web/CLAUDE.md` coherent with the code.

---

## Task 1: Dark theme — `index.css` tokens + sweep hardcoded light literals

**Files:**
- Modify: `apps/web/src/index.css`
- Modify: `apps/web/src/routes/Devcontainers.tsx` (`statusBadgeClass`, lines ~67-79)

**Interfaces:**
- Produces: dark theme tokens consumed app-wide; badge helpers using `bg-accent/15 text-accent` and `bg-bad/15 text-bad` (no light-mode `emerald-100`/`red-100` literals remain anywhere).

- [ ] **Step 1: Swap the theme tokens.** Replace the `@theme` block and `body` color in `apps/web/src/index.css`:

```css
@import "tailwindcss";

@theme {
  --color-bg: #15151c;
  --color-surface-sidebar: #1b1b24;
  --color-surface-rail: #1b1b24;
  --color-surface-muted: #23232f;
  --color-border: #30303f;
  --color-text: #f4f4f6;
  --color-text-muted: #9a9aa8;
  --color-text-subtle: #7c7c8a;
  --color-accent: #3ddc84;
  --color-accent-bg: #18331f;
  --color-ok: #3ddc84;
  --color-bad: #f87171;

  --font-sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

html, body, #root {
  height: 100%;
}

body {
  margin: 0;
  background: var(--color-bg);
  color: var(--color-text-muted);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

- [ ] **Step 2: Remap the hardcoded badge palette in `Devcontainers.tsx`.** Replace `statusBadgeClass`:

```ts
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-accent/15 text-accent'
    case 'starting':
    case 'stopping':
      return 'bg-accent/15 text-accent'
    case 'error':
      return 'bg-bad/15 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}
```

- [ ] **Step 3: Find any remaining light-mode literals.**

Run: `cd apps/web && grep -rnE "emerald-[0-9]|red-100|bg-white|text-white" src/routes src/components` 
Expected: matches only in `Devcontainers.tsx`/`DevcontainerDetail.tsx`. For each match outside `DevcontainerDetail.tsx` (which is rebuilt later), replace `bg-white`→`bg-surface-muted`, `text-white` on accent buttons is fine (green button, dark text would be `text-bg`; prefer `text-bg` for buttons with `bg-accent`). Leave `DevcontainerDetail.tsx` untouched here — it is replaced in Task 8.

- [ ] **Step 4: Verify build.**

Run: `cd apps/web && pnpm build`
Expected: succeeds (tsc + vite), no errors.

- [ ] **Step 5: Commit.**

```bash
git add apps/web/src/index.css apps/web/src/routes/Devcontainers.tsx
git commit -m "feat(web): dark slate+green theme tokens"
```

---

## Task 2: API types + endpoint functions

**Files:**
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/lib/api/endpoints.ts`

**Interfaces:**
- Produces: `HarnessStatus`, `HarnessStatusList`, `DelegatedRunStatus`, `DelegatedRun`, `DelegatedRunList` types; endpoint fns `fetchHarnesses(id)`, `installHarness(id,name)`, `authenticateHarness(id,name)`, `fetchDelegatedRuns(id)`, `stopDelegatedRun(id,runId)`.

- [ ] **Step 1: Add DTO types** to the end of `apps/web/src/lib/api/types.ts` (before the error-envelope section):

```ts
// Coding-harness status (runtime HarnessStatus, ADR-0012).
export interface HarnessStatus {
  name: string
  installed: boolean
  authenticated: boolean
}

export interface HarnessStatusList {
  items: HarnessStatus[]
}

// Delegated runs (runtime DelegatedRunManager, ADR-0013).
export type DelegatedRunStatus = 'running' | 'completed' | 'failed' | 'stopped'

export interface DelegatedRun {
  run_id: string
  harness: string
  model: string
  status: DelegatedRunStatus
  result: string | null
  error: Record<string, unknown> | null
  started_at: string
}

export interface DelegatedRunList {
  items: DelegatedRun[]
}
```

- [ ] **Step 2: Add endpoint functions** to `apps/web/src/lib/api/endpoints.ts`. Add to the type import block: `DelegatedRun`, `DelegatedRunList`, `HarnessStatus`, `HarnessStatusList`. Append the functions:

```ts
export const fetchHarnesses = (devcontainerId: string): Promise<HarnessStatusList> =>
  getJson(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses`)

export const installHarness = (devcontainerId: string, name: string): Promise<HarnessStatus> =>
  sendJson<HarnessStatus>(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/${encodeURIComponent(name)}/install`, 'POST') as Promise<HarnessStatus>

export const authenticateHarness = (devcontainerId: string, name: string): Promise<HarnessStatus> =>
  sendJson<HarnessStatus>(`/devcontainers/${encodeURIComponent(devcontainerId)}/harnesses/${encodeURIComponent(name)}/authenticate`, 'POST') as Promise<HarnessStatus>

export const fetchDelegatedRuns = (devcontainerId: string): Promise<DelegatedRunList> =>
  getJson(`/devcontainers/${encodeURIComponent(devcontainerId)}/delegated-runs`)

export const stopDelegatedRun = (devcontainerId: string, runId: string): Promise<DelegatedRun> =>
  sendJson<DelegatedRun>(`/devcontainers/${encodeURIComponent(devcontainerId)}/delegated-runs/${encodeURIComponent(runId)}/stop`, 'POST') as Promise<DelegatedRun>
```

- [ ] **Step 3: Verify typecheck.**

Run: `cd apps/web && pnpm typecheck`
Expected: succeeds (these are additive; consumers come later).

- [ ] **Step 4: Commit.**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/lib/api/endpoints.ts
git commit -m "feat(web): harness + delegated-run API types and endpoints"
```

---

## Task 3: Mock seeds + harness mutable state

**Files:**
- Modify: `apps/web/src/mock/state/seeds.ts`
- Create: `apps/web/src/mock/state/harnesses.ts`
- Create: `apps/web/src/mock/__tests__/harnesses.test.ts`

**Interfaces:**
- Consumes: `HarnessStatus`, `HarnessStatusList` (Task 2).
- Produces: `seedHarnesses`; `listHarnesses(id)`, `installHarness(id,name)`, `authenticateHarness(id,name)`, `resetHarnesses()`, `NotFoundError` from `state/harnesses`.

- [ ] **Step 1: Add harness seeds** to `apps/web/src/mock/state/seeds.ts`. Extend the type import to include `HarnessStatus` and append:

```ts
// Harness status per devcontainer. dc-seed-0001 spans all three states for inspection.
export const seedHarnesses: Record<string, HarnessStatus[]> = {
  'dc-seed-0001': [
    { name: 'claude-code', installed: true, authenticated: true },
    { name: 'codex', installed: true, authenticated: false },
    { name: 'cursor', installed: false, authenticated: false },
  ],
  'dc-seed-0002': [
    { name: 'claude-code', installed: true, authenticated: false },
    { name: 'codex', installed: false, authenticated: false },
    { name: 'cursor', installed: false, authenticated: false },
  ],
}
```

- [ ] **Step 2: Write the failing test** `apps/web/src/mock/__tests__/harnesses.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { listHarnesses, installHarness, authenticateHarness, resetHarnesses, NotFoundError } from '../state/harnesses'

beforeEach(() => resetHarnesses())

describe('harness mock state', () => {
  it('lists seeded harnesses for a devcontainer', () => {
    const { items } = listHarnesses('dc-seed-0001')
    expect(items.map((h) => h.name)).toEqual(['claude-code', 'codex', 'cursor'])
  })

  it('returns empty items for an unseeded devcontainer', () => {
    expect(listHarnesses('dc-unknown').items).toEqual([])
  })

  it('install flips installed=true and persists', () => {
    expect(installHarness('dc-seed-0001', 'cursor').installed).toBe(true)
    expect(listHarnesses('dc-seed-0001').items.find((h) => h.name === 'cursor')!.installed).toBe(true)
  })

  it('authenticate flips authenticated=true and persists', () => {
    expect(authenticateHarness('dc-seed-0001', 'codex').authenticated).toBe(true)
    expect(listHarnesses('dc-seed-0001').items.find((h) => h.name === 'codex')!.authenticated).toBe(true)
  })

  it('throws NotFoundError for an unknown harness', () => {
    expect(() => installHarness('dc-seed-0001', 'nope')).toThrow(NotFoundError)
  })

  it('resetHarnesses restores seed state', () => {
    installHarness('dc-seed-0001', 'cursor')
    resetHarnesses()
    expect(listHarnesses('dc-seed-0001').items.find((h) => h.name === 'cursor')!.installed).toBe(false)
  })
})
```

- [ ] **Step 2b: Run test to verify it fails.**

Run: `cd apps/web && pnpm test -- harnesses`
Expected: FAIL — cannot resolve `../state/harnesses`.

- [ ] **Step 3: Implement** `apps/web/src/mock/state/harnesses.ts`:

```ts
import type { HarnessStatus, HarnessStatusList } from '../../lib/api/types'
import { seedHarnesses } from './seeds'

export class NotFoundError extends Error {
  readonly code = 'HARNESS_NOT_FOUND'
  constructor(name: string) {
    super(`Harness not found: ${name}`)
  }
}

function clone(src: Record<string, HarnessStatus[]>): Record<string, HarnessStatus[]> {
  return Object.fromEntries(Object.entries(src).map(([k, v]) => [k, v.map((h) => ({ ...h }))]))
}

let store: Record<string, HarnessStatus[]> = clone(seedHarnesses)

export function resetHarnesses(): void {
  store = clone(seedHarnesses)
}

export function listHarnesses(devcontainerId: string): HarnessStatusList {
  return { items: (store[devcontainerId] ?? []).map((h) => ({ ...h })) }
}

function find(devcontainerId: string, name: string): HarnessStatus {
  const h = (store[devcontainerId] ?? []).find((x) => x.name === name)
  if (!h) throw new NotFoundError(name)
  return h
}

export function installHarness(devcontainerId: string, name: string): HarnessStatus {
  const h = find(devcontainerId, name)
  h.installed = true
  return { ...h }
}

export function authenticateHarness(devcontainerId: string, name: string): HarnessStatus {
  const h = find(devcontainerId, name)
  h.authenticated = true
  return { ...h }
}
```

- [ ] **Step 4: Run test to verify it passes.**

Run: `cd apps/web && pnpm test -- harnesses`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit.**

```bash
git add apps/web/src/mock/state/seeds.ts apps/web/src/mock/state/harnesses.ts apps/web/src/mock/__tests__/harnesses.test.ts
git commit -m "feat(web): harness mock state + seeds"
```

---

## Task 4: Mock seeds + delegated-runs mutable state

**Files:**
- Modify: `apps/web/src/mock/state/seeds.ts`
- Create: `apps/web/src/mock/state/delegatedRuns.ts`
- Create: `apps/web/src/mock/__tests__/delegatedRuns.test.ts`

**Interfaces:**
- Consumes: `DelegatedRun`, `DelegatedRunList` (Task 2).
- Produces: `seedDelegatedRuns`; `listDelegatedRuns(id)`, `stopDelegatedRun(id,runId)`, `resetDelegatedRuns()`, `NotFoundError` from `state/delegatedRuns`.

- [ ] **Step 1: Add delegated-run seeds** to `apps/web/src/mock/state/seeds.ts`. Extend the type import to include `DelegatedRun` and append:

```ts
// Delegated runs per devcontainer — one of each terminal state plus a live one.
export const seedDelegatedRuns: Record<string, DelegatedRun[]> = {
  'dc-seed-0001': [
    { run_id: 'run-4', harness: 'codex', model: 'gpt-5-codex', status: 'running', result: null, error: null, started_at: '2024-01-15T10:00:00.000Z' },
    { run_id: 'run-3', harness: 'claude-code', model: 'opus-4.8', status: 'completed', result: 'Refactored auth module; 3 files changed, tests pass.', error: null, started_at: '2024-01-15T09:55:00.000Z' },
    { run_id: 'run-2', harness: 'cursor', model: 'auto', status: 'failed', result: null, error: { exit_code: 1, stderr_tail: 'ENOENT: package.json not found' }, started_at: '2024-01-15T09:40:00.000Z' },
  ],
}
```

- [ ] **Step 2: Write the failing test** `apps/web/src/mock/__tests__/delegatedRuns.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { listDelegatedRuns, stopDelegatedRun, resetDelegatedRuns, NotFoundError } from '../state/delegatedRuns'

beforeEach(() => resetDelegatedRuns())

describe('delegated-run mock state', () => {
  it('lists seeded runs newest-first as seeded', () => {
    expect(listDelegatedRuns('dc-seed-0001').items.map((r) => r.run_id)).toEqual(['run-4', 'run-3', 'run-2'])
  })

  it('returns empty items for an unseeded devcontainer', () => {
    expect(listDelegatedRuns('dc-unknown').items).toEqual([])
  })

  it('stop flips a running run to stopped and persists', () => {
    expect(stopDelegatedRun('dc-seed-0001', 'run-4').status).toBe('stopped')
    expect(listDelegatedRuns('dc-seed-0001').items.find((r) => r.run_id === 'run-4')!.status).toBe('stopped')
  })

  it('stop on a finished run leaves its status unchanged', () => {
    expect(stopDelegatedRun('dc-seed-0001', 'run-3').status).toBe('completed')
  })

  it('throws NotFoundError for an unknown run', () => {
    expect(() => stopDelegatedRun('dc-seed-0001', 'nope')).toThrow(NotFoundError)
  })
})
```

- [ ] **Step 2b: Run test to verify it fails.**

Run: `cd apps/web && pnpm test -- delegatedRuns`
Expected: FAIL — cannot resolve `../state/delegatedRuns`.

- [ ] **Step 3: Implement** `apps/web/src/mock/state/delegatedRuns.ts`:

```ts
import type { DelegatedRun, DelegatedRunList } from '../../lib/api/types'
import { seedDelegatedRuns } from './seeds'

export class NotFoundError extends Error {
  readonly code = 'DELEGATED_RUN_NOT_FOUND'
  constructor(runId: string) {
    super(`Delegated run not found: ${runId}`)
  }
}

function clone(src: Record<string, DelegatedRun[]>): Record<string, DelegatedRun[]> {
  return Object.fromEntries(Object.entries(src).map(([k, v]) => [k, v.map((r) => ({ ...r }))]))
}

let store: Record<string, DelegatedRun[]> = clone(seedDelegatedRuns)

export function resetDelegatedRuns(): void {
  store = clone(seedDelegatedRuns)
}

export function listDelegatedRuns(devcontainerId: string): DelegatedRunList {
  return { items: (store[devcontainerId] ?? []).map((r) => ({ ...r })) }
}

export function stopDelegatedRun(devcontainerId: string, runId: string): DelegatedRun {
  const r = (store[devcontainerId] ?? []).find((x) => x.run_id === runId)
  if (!r) throw new NotFoundError(runId)
  if (r.status === 'running') r.status = 'stopped'
  return { ...r }
}
```

- [ ] **Step 4: Run test to verify it passes.**

Run: `cd apps/web && pnpm test -- delegatedRuns`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit.**

```bash
git add apps/web/src/mock/state/seeds.ts apps/web/src/mock/state/delegatedRuns.ts apps/web/src/mock/__tests__/delegatedRuns.test.ts
git commit -m "feat(web): delegated-run mock state + seeds"
```

---

## Task 5: Mock handlers, invalidation scopes, fixtures + RailMock controls

**Files:**
- Modify: `apps/web/src/lib/events/types.ts` (add scopes)
- Modify: `apps/web/src/mock/handlers.ts`
- Modify: `apps/web/src/mock/RailMock.tsx`
- Create: `apps/web/src/mock/__tests__/harnessHandlers.test.ts`

**Interfaces:**
- Consumes: `listHarnesses`/`installHarness`/`authenticateHarness` (Task 3), `listDelegatedRuns`/`stopDelegatedRun` (Task 4), `emitInvalidation` (existing).
- Produces: five MSW routes under `*/api/v1/devcontainers/...`; `Scope` union extended with `'harnesses' | 'delegated_runs'`.

- [ ] **Step 1: Add the two scopes** in `apps/web/src/lib/events/types.ts`:

```ts
export type Scope = 'devcontainers' | 'agent_sessions' | 'runtime' | 'harnesses' | 'delegated_runs'
```

- [ ] **Step 2: Write the failing handler test** `apps/web/src/mock/__tests__/harnessHandlers.test.ts`:

```ts
import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers } from '../handlers'
import { setScenario, resetScenario } from '../scenario'
import { resetHarnesses } from '../state/harnesses'
import { resetDelegatedRuns } from '../state/delegatedRuns'

const server = setupServer(...handlers)
beforeAll(() => server.listen())
beforeEach(() => { resetScenario(); resetHarnesses(); resetDelegatedRuns() })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const get = (p: string) => fetch(`http://localhost${p}`)
const post = (p: string) => fetch(`http://localhost${p}`, { method: 'POST' })

describe('harness + delegated-run handlers', () => {
  it('GET /harnesses returns seeded list', async () => {
    const body = await (await get('/api/v1/devcontainers/dc-seed-0001/harnesses')).json()
    expect(body.items.map((h: { name: string }) => h.name)).toContain('codex')
  })

  it('GET /harnesses 404s for unknown devcontainer', async () => {
    const res = await get('/api/v1/devcontainers/nope/harnesses')
    expect(res.status).toBe(404)
    expect((await res.json()).error.code).toBe('DEVCONTAINER_NOT_FOUND')
  })

  it('POST install flips installed and refetch reflects it', async () => {
    expect((await (await post('/api/v1/devcontainers/dc-seed-0001/harnesses/cursor/install')).json()).installed).toBe(true)
    const list = await (await get('/api/v1/devcontainers/dc-seed-0001/harnesses')).json()
    expect(list.items.find((h: { name: string }) => h.name === 'cursor').installed).toBe(true)
  })

  it('POST authenticate flips authenticated', async () => {
    expect((await (await post('/api/v1/devcontainers/dc-seed-0001/harnesses/codex/authenticate')).json()).authenticated).toBe(true)
  })

  it('GET /delegated-runs returns seeded runs', async () => {
    const body = await (await get('/api/v1/devcontainers/dc-seed-0001/delegated-runs')).json()
    expect(body.items.map((r: { run_id: string }) => r.run_id)).toEqual(['run-4', 'run-3', 'run-2'])
  })

  it('POST stop flips a running run to stopped', async () => {
    const body = await (await post('/api/v1/devcontainers/dc-seed-0001/delegated-runs/run-4/stop')).json()
    expect(body.status).toBe('stopped')
  })
})
```

- [ ] **Step 2b: Run test to verify it fails.**

Run: `cd apps/web && pnpm test -- harnessHandlers`
Expected: FAIL — routes not registered (404 / unexpected).

- [ ] **Step 3: Register handlers.** In `apps/web/src/mock/handlers.ts`: add imports near the top —

```ts
import * as hn from './state/harnesses'
import * as dr from './state/delegatedRuns'
```

Then append these five handlers inside the `devcontainerHandlers` array (after the `stop` handler, before the closing `]`):

```ts
  http.get('*/api/v1/devcontainers/:id/harnesses', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      dc.getDevcontainer(params.id as string)
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
    if (getScenario() === 'empty') return HttpResponse.json({ items: [] })
    return HttpResponse.json(hn.listHarnesses(params.id as string))
  }),

  http.post('*/api/v1/devcontainers/:id/harnesses/:name/install', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND', 'HARNESS_NOT_FOUND')
    if (failure) return failure
    try {
      const status = hn.installHarness(params.id as string, params.name as string)
      emitInvalidation('harnesses')
      return HttpResponse.json(status)
    } catch (e) {
      if (e instanceof hn.NotFoundError) {
        return HttpResponse.json(errorEnvelope('HARNESS_NOT_FOUND', e.message), { status: 404 })
      }
      throw e
    }
  }),

  http.post('*/api/v1/devcontainers/:id/harnesses/:name/authenticate', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND', 'HARNESS_NOT_FOUND')
    if (failure) return failure
    try {
      const status = hn.authenticateHarness(params.id as string, params.name as string)
      emitInvalidation('harnesses')
      return HttpResponse.json(status)
    } catch (e) {
      if (e instanceof hn.NotFoundError) {
        return HttpResponse.json(errorEnvelope('HARNESS_NOT_FOUND', e.message), { status: 404 })
      }
      throw e
    }
  }),

  http.get('*/api/v1/devcontainers/:id/delegated-runs', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      dc.getDevcontainer(params.id as string)
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
    if (getScenario() === 'empty') return HttpResponse.json({ items: [] })
    return HttpResponse.json(dr.listDelegatedRuns(params.id as string))
  }),

  http.post('*/api/v1/devcontainers/:id/delegated-runs/:runId/stop', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND', 'DELEGATED_RUN_NOT_FOUND')
    if (failure) return failure
    try {
      const run = dr.stopDelegatedRun(params.id as string, params.runId as string)
      emitInvalidation('delegated_runs')
      return HttpResponse.json(run)
    } catch (e) {
      if (e instanceof dr.NotFoundError) {
        return HttpResponse.json(errorEnvelope('DELEGATED_RUN_NOT_FOUND', e.message), { status: 404 })
      }
      throw e
    }
  }),
```

- [ ] **Step 4: Run test to verify it passes.**

Run: `cd apps/web && pnpm test -- harnessHandlers`
Expected: PASS (6 tests).

- [ ] **Step 5: Add RailMock emit buttons.** In `apps/web/src/mock/RailMock.tsx`, extend the scopes list:

```ts
const SCOPES: Scope[] = ['devcontainers', 'agent_sessions', 'runtime', 'harnesses', 'delegated_runs']
```

- [ ] **Step 6: Verify full suite + build.**

Run: `cd apps/web && pnpm test && pnpm build`
Expected: all green.

- [ ] **Step 7: Commit.**

```bash
git add apps/web/src/lib/events/types.ts apps/web/src/mock/handlers.ts apps/web/src/mock/RailMock.tsx apps/web/src/mock/__tests__/harnessHandlers.test.ts
git commit -m "feat(web): mock harness + delegated-run endpoints, scopes, rail controls"
```

---

## Task 6: HarnessList component

**Files:**
- Create: `apps/web/src/components/HarnessList.tsx`
- Create: `apps/web/src/components/__tests__/HarnessList.test.tsx`

**Interfaces:**
- Consumes: `HarnessStatus` (Task 2), `installHarness`/`authenticateHarness` (Task 2), `cn`.
- Produces: `HarnessList({ devcontainerId, harnesses, onChange })` — `harnesses: HarnessStatus[]`, `onChange: () => void`.

- [ ] **Step 1: Write the failing test** `apps/web/src/components/__tests__/HarnessList.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { HarnessList } from '../HarnessList'
import type { HarnessStatus } from '../../lib/api/types'

const harnesses: HarnessStatus[] = [
  { name: 'claude-code', installed: true, authenticated: true },
  { name: 'codex', installed: true, authenticated: false },
  { name: 'cursor', installed: false, authenticated: false },
]

function setup() {
  render(<HarnessList devcontainerId="dc-seed-0001" harnesses={harnesses} onChange={() => {}} />)
}

describe('HarnessList', () => {
  it('renders a row per harness', () => {
    setup()
    expect(screen.getByText('claude-code')).toBeTruthy()
    expect(screen.getByText('codex')).toBeTruthy()
    expect(screen.getByText('cursor')).toBeTruthy()
  })

  it('offers Authenticate on an installed-but-unauthenticated harness', () => {
    setup()
    expect(screen.getByTitle('Authenticate codex')).toBeTruthy()
  })

  it('offers Install on a not-installed harness', () => {
    setup()
    expect(screen.getByTitle('Install cursor')).toBeTruthy()
  })

  it('disables Authenticate until the harness is installed', () => {
    setup()
    const btn = screen.getByTitle('Install cursor first') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})
```

Note: `@testing-library/jest-dom` is not set up; assert on truthiness and DOM props (`.disabled`) rather than `toBeInTheDocument()`.

- [ ] **Step 1b: Run test to verify it fails.**

Run: `cd apps/web && pnpm test -- HarnessList`
Expected: FAIL — cannot resolve `../HarnessList`.

- [ ] **Step 2: Implement** `apps/web/src/components/HarnessList.tsx`:

```tsx
import { useState } from 'react'
import type { HarnessStatus } from '../lib/api/types'
import { installHarness, authenticateHarness } from '../lib/api'
import { cn } from '../lib/cn'

const checkIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const downloadIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
)

const loginIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
    <polyline points="10 17 15 12 10 7" />
    <line x1="15" y1="12" x2="3" y2="12" />
  </svg>
)

function Tick({ label }: { label: string }) {
  return (
    <span title={label} className="inline-flex h-6 w-6 items-center justify-center text-accent">
      {checkIcon}
    </span>
  )
}

function ActionIcon({ title, disabled, busy, onClick, children }: {
  title: string
  disabled?: boolean
  busy?: boolean
  onClick?: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled || busy}
      onClick={onClick}
      className={cn(
        'inline-flex h-6 w-6 items-center justify-center rounded-md border',
        disabled
          ? 'cursor-not-allowed border-border text-text-subtle opacity-50'
          : 'cursor-pointer border-border text-text hover:bg-surface-muted',
      )}
    >
      {children}
    </button>
  )
}

export function HarnessList({ devcontainerId, harnesses, onChange }: {
  devcontainerId: string
  harnesses: HarnessStatus[]
  onChange: () => void
}) {
  const [busy, setBusy] = useState<string | null>(null)

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key)
    try {
      await fn()
      onChange()
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-surface-rail">
      <div className="grid grid-cols-[1fr_120px_120px] border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.05em] text-text-subtle">
        <span>Harness</span>
        <span className="text-center">Installed</span>
        <span className="text-center">Authenticated</span>
      </div>
      {harnesses.length === 0 ? (
        <p className="px-3 py-4 text-[13px] text-text-muted">No harnesses reported.</p>
      ) : (
        harnesses.map((h) => (
          <div key={h.name} className="grid grid-cols-[1fr_120px_120px] items-center border-b border-border px-3 py-3 last:border-b-0">
            <span className="text-[13px] font-medium text-text">{h.name}</span>
            <span className="flex justify-center">
              {h.installed ? (
                <Tick label="Installed" />
              ) : (
                <ActionIcon
                  title={`Install ${h.name}`}
                  busy={busy === `install:${h.name}`}
                  onClick={() => run(`install:${h.name}`, () => installHarness(devcontainerId, h.name))}
                >
                  {downloadIcon}
                </ActionIcon>
              )}
            </span>
            <span className="flex justify-center">
              {h.authenticated ? (
                <Tick label="Authenticated" />
              ) : (
                <ActionIcon
                  title={h.installed ? `Authenticate ${h.name}` : `Install ${h.name} first`}
                  disabled={!h.installed}
                  busy={busy === `auth:${h.name}`}
                  onClick={() => run(`auth:${h.name}`, () => authenticateHarness(devcontainerId, h.name))}
                >
                  {loginIcon}
                </ActionIcon>
              )}
            </span>
          </div>
        ))
      )}
    </div>
  )
}
```

- [ ] **Step 3: Run test to verify it passes.**

Run: `cd apps/web && pnpm test -- HarnessList`
Expected: PASS (4 tests).

- [ ] **Step 4: Commit.**

```bash
git add apps/web/src/components/HarnessList.tsx apps/web/src/components/__tests__/HarnessList.test.tsx
git commit -m "feat(web): harness list component"
```

---

## Task 7: DelegatedRuns component

**Files:**
- Create: `apps/web/src/components/DelegatedRuns.tsx`
- Create: `apps/web/src/components/__tests__/DelegatedRuns.test.tsx`

**Interfaces:**
- Consumes: `DelegatedRun` (Task 2), `stopDelegatedRun` (Task 2), `formatRelativeTime` (`lib/time`), `cn`.
- Produces: `DelegatedRuns({ devcontainerId, runs, onChange })` — `runs: DelegatedRun[]`, `onChange: () => void`.

- [ ] **Step 1: Write the failing test** `apps/web/src/components/__tests__/DelegatedRuns.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DelegatedRuns } from '../DelegatedRuns'
import type { DelegatedRun } from '../../lib/api/types'

const runs: DelegatedRun[] = [
  { run_id: 'run-4', harness: 'codex', model: 'gpt-5-codex', status: 'running', result: null, error: null, started_at: '2024-01-15T10:00:00.000Z' },
  { run_id: 'run-2', harness: 'cursor', model: 'auto', status: 'failed', result: null, error: { stderr_tail: 'boom' }, started_at: '2024-01-15T09:40:00.000Z' },
]

describe('DelegatedRuns', () => {
  it('shows a quiet empty state when there are no runs', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={[]} onChange={() => {}} />)
    expect(screen.getByText(/No delegated runs/i)).toBeTruthy()
  })

  it('renders a row per run with its status', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={runs} onChange={() => {}} />)
    expect(screen.getByText('run-4')).toBeTruthy()
    expect(screen.getByText('running')).toBeTruthy()
    expect(screen.getByText('failed')).toBeTruthy()
  })

  it('offers Stop only on running rows', () => {
    render(<DelegatedRuns devcontainerId="dc-seed-0001" runs={runs} onChange={() => {}} />)
    expect(screen.getByTitle('Stop run-4')).toBeTruthy()
    expect(screen.queryByTitle('Stop run-2')).toBeNull()
  })
})
```

- [ ] **Step 1b: Run test to verify it fails.**

Run: `cd apps/web && pnpm test -- DelegatedRuns`
Expected: FAIL — cannot resolve `../DelegatedRuns`.

- [ ] **Step 2: Implement** `apps/web/src/components/DelegatedRuns.tsx`:

```tsx
import { useState } from 'react'
import type { DelegatedRun } from '../lib/api/types'
import { stopDelegatedRun } from '../lib/api'
import { formatRelativeTime } from '../lib/time'
import { cn } from '../lib/cn'

function badgeClass(status: DelegatedRun['status']): string {
  switch (status) {
    case 'running':
      return 'bg-accent/15 text-accent'
    case 'failed':
      return 'bg-bad/15 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

function RunRow({ devcontainerId, run, onChange }: {
  devcontainerId: string
  run: DelegatedRun
  onChange: () => void
}) {
  const [busy, setBusy] = useState(false)
  const detail = run.status === 'failed' ? errorText(run.error) : run.result

  async function stop() {
    setBusy(true)
    try {
      await stopDelegatedRun(devcontainerId, run.run_id)
      onChange()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface-muted px-3 py-2.5">
      <div className="flex items-center gap-2">
        {run.status === 'running' && <span className="h-2 w-2 shrink-0 rounded-full bg-accent" />}
        <span className="font-mono text-[12px] font-semibold text-text">{run.run_id}</span>
        <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', badgeClass(run.status))}>
          {run.status}
        </span>
        {run.status === 'running' && (
          <button
            type="button"
            title={`Stop ${run.run_id}`}
            disabled={busy}
            onClick={stop}
            className="ml-auto rounded-md border border-border px-2 py-0.5 text-[11px] text-text hover:bg-surface-rail disabled:opacity-40"
          >
            Stop
          </button>
        )}
      </div>
      <div className="mt-1 text-[11px] text-text-subtle">
        {run.harness} · {run.model} · {formatRelativeTime(run.started_at)}
      </div>
      {detail && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] text-text-muted">
            {run.status === 'failed' ? 'error' : 'result'}
          </summary>
          <pre className={cn('mt-1 overflow-x-auto rounded-md border border-border bg-bg p-2 text-[11px]', run.status === 'failed' ? 'text-bad' : 'text-text-muted')}>
            {detail}
          </pre>
        </details>
      )}
    </div>
  )
}

function errorText(error: DelegatedRun['error']): string | null {
  if (!error) return null
  const code = error.exit_code
  const tail = error.stderr_tail
  return [code != null ? `exit ${code}` : null, typeof tail === 'string' ? tail : null].filter(Boolean).join(' · ') || JSON.stringify(error)
}

export function DelegatedRuns({ devcontainerId, runs, onChange }: {
  devcontainerId: string
  runs: DelegatedRun[]
  onChange: () => void
}) {
  if (runs.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-[13px] text-text-muted">
        No delegated runs — the harness will list them here when it spawns one.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      {runs.map((run) => (
        <RunRow key={run.run_id} devcontainerId={devcontainerId} run={run} onChange={onChange} />
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Run test to verify it passes.**

Run: `cd apps/web && pnpm test -- DelegatedRuns`
Expected: PASS (3 tests).

- [ ] **Step 4: Commit.**

```bash
git add apps/web/src/components/DelegatedRuns.tsx apps/web/src/components/__tests__/DelegatedRuns.test.tsx
git commit -m "feat(web): delegated-runs feed component"
```

---

## Task 8: Rebuild DevcontainerDetail (lifecycle header + two-column layout)

**Files:**
- Replace: `apps/web/src/routes/DevcontainerDetail.tsx` (full rewrite — drops all chat/transcript/session code)

**Interfaces:**
- Consumes: `fetchDevcontainer`, `startDevcontainer`, `stopDevcontainer`, `fetchHarnesses`, `fetchDelegatedRuns` (Tasks 2), `HarnessList` (Task 6), `DelegatedRuns` (Task 7), `PageHeader`, `QueryBoundary`, `ErrorState`, `useApiQuery`, `useSseInvalidation`, `ApiError`, `loadError`, `formatRelativeTime`, `cn`.

- [ ] **Step 1: Replace the file** `apps/web/src/routes/DevcontainerDetail.tsx` entirely with:

```tsx
import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { PageHeader } from '../components/PageHeader'
import { ErrorState } from '../components/ErrorState'
import { QueryBoundary } from '../components/QueryBoundary'
import { HarnessList } from '../components/HarnessList'
import { DelegatedRuns } from '../components/DelegatedRuns'
import {
  fetchDevcontainer,
  startDevcontainer,
  stopDevcontainer,
  fetchHarnesses,
  fetchDelegatedRuns,
  useApiQuery,
  ApiError,
} from '../lib/api'
import type { DevcontainerView } from '../lib/api/types'
import { formatRelativeTime } from '../lib/time'
import { useSseInvalidation } from '../lib/events'
import { loadError } from '../lib/copy'
import { cn } from '../lib/cn'

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-accent/15 text-accent'
    case 'starting':
    case 'stopping':
      return 'bg-accent/15 text-accent'
    case 'error':
      return 'bg-bad/15 text-bad'
    default:
      return 'bg-surface-muted text-text-muted'
  }
}

const RUNNING = new Set(['running', 'starting', 'stopping'])

function ConnDot({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-text-muted">
      <span className={cn('h-2 w-2 rounded-full', ok ? 'bg-ok' : 'bg-text-subtle')} />
      {label}
    </span>
  )
}

function LifecycleHeader({ dc, onChange }: { dc: DevcontainerView; onChange: () => void }) {
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const running = RUNNING.has(dc.status)

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    try {
      await fn()
      onChange()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border-b border-border bg-surface-rail px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-[15px] font-semibold text-text">{dc.name}</span>
        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', statusBadgeClass(dc.status))}>
          {dc.status}
        </span>
        <ConnDot label="worker" ok={dc.runtime.worker_connected} />
        <ConnDot label="agent" ok={dc.runtime.agent_connected} />
        <div className="ml-auto flex items-center gap-2">
          {dc.status === 'running' ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => act(() => stopDevcontainer(dc.id))}
              className="rounded-lg border border-border px-3 py-1.5 text-[13px] font-medium text-text hover:bg-surface-muted disabled:opacity-40"
            >
              Stop
            </button>
          ) : (
            <button
              type="button"
              disabled={busy || running}
              onClick={() => act(() => startDevcontainer(dc.id))}
              className="rounded-lg bg-accent px-3 py-1.5 text-[13px] font-medium text-bg hover:bg-accent/90 disabled:opacity-40"
            >
              Start
            </button>
          )}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[11px] text-text-muted hover:text-text"
          >
            {expanded ? '▾' : '▸'} details
          </button>
        </div>
      </div>
      {expanded && (
        <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-2 border-t border-border pt-3 text-[13px]">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-text-subtle">Local path</div>
            <div className="mt-0.5 text-text">{dc.local_path}</div>
          </div>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-text-subtle">Created</div>
            <div className="mt-0.5 text-text">{formatRelativeTime(dc.created_at)}</div>
          </div>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.05em] text-text-subtle">Updated</div>
            <div className="mt-0.5 text-text">{formatRelativeTime(dc.updated_at)}</div>
          </div>
        </div>
      )}
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{children}</h3>
}

function ControlPanel({ dc }: { dc: DevcontainerView }) {
  const { register } = useSseInvalidation()
  const { state: harnessState, refetch: refetchHarnesses } = useApiQuery(() => fetchHarnesses(dc.id), [dc.id])
  const { state: runsState, refetch: refetchRuns } = useApiQuery(() => fetchDelegatedRuns(dc.id), [dc.id])

  useEffect(() => register('harnesses', refetchHarnesses), [register, refetchHarnesses])
  useEffect(() => register('delegated_runs', refetchRuns), [register, refetchRuns])

  return (
    <div className="grid grid-cols-1 gap-6 p-4 lg:grid-cols-2">
      <section>
        <SectionTitle>Coding harnesses</SectionTitle>
        {harnessState.kind === 'ready' ? (
          <HarnessList devcontainerId={dc.id} harnesses={harnessState.data.items} onChange={refetchHarnesses} />
        ) : harnessState.kind === 'error' ? (
          <ErrorState {...loadError('harnesses')} />
        ) : (
          <p className="text-[13px] text-text-muted">Loading harnesses…</p>
        )}
      </section>
      <section>
        <SectionTitle>Delegated runs</SectionTitle>
        {runsState.kind === 'ready' ? (
          <DelegatedRuns devcontainerId={dc.id} runs={runsState.data.items} onChange={refetchRuns} />
        ) : runsState.kind === 'error' ? (
          <ErrorState {...loadError('delegated runs')} />
        ) : (
          <p className="text-[13px] text-text-muted">Loading runs…</p>
        )}
      </section>
    </div>
  )
}

function errorElement(error: unknown) {
  if (error instanceof ApiError && error.code === 'DEVCONTAINER_NOT_FOUND') {
    return <ErrorState title="Devcontainer not found" helper="This devcontainer doesn't exist or has been deleted." />
  }
  return <ErrorState {...loadError('devcontainer')} />
}

export function DevcontainerDetail() {
  const { id } = useParams<{ id: string }>()
  const { register } = useSseInvalidation()
  const { state, refetch } = useApiQuery(() => fetchDevcontainer(id!), [id])

  useEffect(() => register('devcontainers', refetch), [register, refetch])

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0">
        <PageHeader title="Devcontainer" crumbs="Detail" />
      </div>
      <QueryBoundary state={state} error={errorElement(state.kind === 'error' ? state.error : null)}>
        {(dc) => (
          <div className="min-h-0 flex-1 overflow-auto">
            <LifecycleHeader dc={dc} onChange={refetch} />
            <ControlPanel dc={dc} />
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
```

- [ ] **Step 2: (Reference) `loadError(subject: string)`** in `src/lib/copy.ts` accepts any string and returns `{ title, helper }`, so `loadError('harnesses')` / `loadError('delegated runs')` work as written — no change needed.

- [ ] **Step 3: Verify typecheck + build (chat code now unreferenced by the page).**

Run: `cd apps/web && pnpm typecheck && pnpm build`
Expected: succeeds. `lib/stream`, `lib/chat`, and agent-session endpoints are now unused by app code but still present (deleted in Task 9).

- [ ] **Step 4: Run the suite; remove any now-obsolete detail/chat route tests.**

Run: `cd apps/web && pnpm test`
Expected: green. If a pre-existing test imports the old chat detail page internals and fails, delete that test (chat is gone). Do not weaken harness/run tests.

- [ ] **Step 5: Commit.**

```bash
git add apps/web/src/routes/DevcontainerDetail.tsx
git commit -m "feat(web): rebuild devcontainer detail as runtime control panel"
```

---

## Task 9: Delete dead chat/stream/agent-session frontend code

**Files:**
- Delete: `apps/web/src/lib/stream/` (whole dir), `apps/web/src/lib/chat/` (whole dir)
- Delete: `apps/web/src/mock/state/agentSessions.ts`, `apps/web/src/mock/agentSessionStreams.ts`
- Delete tests: `apps/web/src/mock/__tests__/agentSessions.test.ts`, `agentSessionStreams.test.ts`, and any other test that exercises agent sessions / session streams (e.g. `mockSseRefetch.test.tsx` if it is agent-session specific)
- Modify: `apps/web/src/lib/api/types.ts`, `apps/web/src/lib/api/endpoints.ts`, `apps/web/src/mock/handlers.ts`, `apps/web/src/mock/fixtures.ts`, `apps/web/src/mock/state/seeds.ts`, `apps/web/src/mock/RailMock.tsx`, `apps/web/src/lib/events/types.ts`
- Modify docs: `apps/web/CLAUDE.md`

**Interfaces:**
- Produces: a tree with no remaining references to agent sessions, transcripts, or per-session streams.

- [ ] **Step 1: Delete the dead modules and their tests.**

```bash
cd apps/web
git rm -r src/lib/stream src/lib/chat
git rm src/mock/state/agentSessions.ts src/mock/agentSessionStreams.ts
git rm src/mock/__tests__/agentSessions.test.ts src/mock/__tests__/agentSessionStreams.test.ts
```

- [ ] **Step 2: Remove agent-session API surface.**
  - In `src/lib/api/endpoints.ts`: delete `fetchAgentSessions`, `fetchAgentSession`, `startAgentSession`, `stopAgentSession`, `resumeAgentSession`, `deleteAgentSession`, `fetchAgentSessionTranscript`, `openAgentSessionStream`, and now-unused imports.
  - In `src/lib/api/types.ts`: delete `AgentSessionStatus`, `AgentSession`, `AgentSessionDetail`, `AgentSessionList`, `AgentSessionStartBody`, `AgentSessionResumeBody`, `TranscriptTextBlock`, `TranscriptToolUseBlock`, `TranscriptBlock`, `TranscriptTurn`, `TranscriptState`, `RunStartedDelta`, `TextDelta`, `RunEndedDelta`, `ToolUseDelta`, `TurnDelta`, `AgentSessionTranscript`.

- [ ] **Step 3: Remove agent-session mock wiring.**
  - In `src/mock/handlers.ts`: remove `import * as as from './state/agentSessions'`, the `AgentSessionResumeBody`/`AgentSessionStartBody` type imports, and all six agent-session handlers (transcript, get, list, create, resume, stop, delete).
  - In `src/mock/fixtures.ts`: remove the `AgentSessionList` import, `seedAgentSessions` import, and the `agentSessions` export.
  - In `src/mock/state/seeds.ts`: remove `seedAgentSessions`, `seedSession`, and the `AgentSession` type import.
  - In `src/mock/RailMock.tsx`: remove `playSessionStream` import, `LIVE_DEMO_SESSION`, the "Session stream" block and its button, and drop `'agent_sessions'` from `SCOPES`.
  - In `src/lib/events/types.ts`: drop `'agent_sessions'` from `Scope` → `'devcontainers' | 'runtime' | 'harnesses' | 'delegated_runs'`.

- [ ] **Step 4: Catch stragglers.**

Run: `cd apps/web && grep -rniE "agent.?session|transcript|sessionStream|turn.?delta|lib/(stream|chat)" src | grep -v node_modules`
Expected: no matches. Fix any that remain (including stray references in `mock/__tests__/bootstrap.test.tsx`, `MockScenarios.test.tsx`, or `mock/README.md`).

- [ ] **Step 5: Update `apps/web/CLAUDE.md`.** Remove the `src/lib/stream/` and `src/lib/chat/` bullets. Under the mock bullet, replace agent-session store mentions with `state/harnesses.ts` and `state/delegatedRuns.ts`, and note the new endpoints + `harnesses`/`delegated_runs` scopes.

- [ ] **Step 6: Verify suite + build + lint.**

Run: `cd apps/web && pnpm test && pnpm build && pnpm lint`
Expected: all green, no unused-import errors.

- [ ] **Step 7: Commit.**

```bash
git add -A
git commit -m "refactor(web): remove chat/stream/agent-session frontend code"
```

---

## Task 10: Playwright verification + fix

**Files:** none created — interactive verification against `pnpm dev:mock`, fixing any defect found in the files from Tasks 1-9.

**Tooling:** Playwright is not a repo dependency; use the Playwright **MCP** browser tools. Load their schemas first with ToolSearch: `select:mcp__plugin_playwright_playwright__browser_navigate,mcp__plugin_playwright_playwright__browser_snapshot,mcp__plugin_playwright_playwright__browser_take_screenshot,mcp__plugin_playwright_playwright__browser_click,mcp__plugin_playwright_playwright__browser_wait_for`.

- [ ] **Step 1: Start the mock dev server (background).**

Run (background): `cd apps/web && pnpm dev:mock`
Then confirm it is serving: `curl -sf http://localhost:5173 >/dev/null && echo UP` (retry until UP).

- [ ] **Step 2: Open the detail page.** `browser_navigate` → `http://localhost:5173/devcontainers/dc-seed-0001`, then `browser_snapshot`.
Expected in the accessibility tree: lifecycle header showing `my-webapp`, status `running`, worker + agent dots; "Coding harnesses" with rows `claude-code` (two ticks), `codex` (tick + Authenticate), `cursor` (Install + disabled Authenticate); "Delegated runs" showing `run-4` (running, Stop), `run-3` (completed), `run-2` (failed).

- [ ] **Step 3: Capture a screenshot** with `browser_take_screenshot` and confirm the dark slate background + green accents render (no light/white panels).

- [ ] **Step 4: Exercise interactions.**
  - `browser_click` the `Install cursor` icon → snapshot → cursor Installed becomes a green tick and Authenticate becomes enabled.
  - `browser_click` `Authenticate codex` → snapshot → codex Authenticated becomes a green tick.
  - `browser_click` `Stop run-4` → snapshot → run-4 status becomes `stopped` and Stop disappears.

- [ ] **Step 5: Spot-check other routes for theme coherence.** Navigate to `http://localhost:5173/devcontainers` and `http://localhost:5173/settings`, screenshot each — confirm dark theme everywhere, no leftover light-mode badges/panels.

- [ ] **Step 6: Empty-state check.** Navigate to `http://localhost:5173/devcontainers/dc-seed-0002` → harnesses show claude-code (installed, Authenticate), and delegated runs show the quiet empty state ("No delegated runs…").

- [ ] **Step 7: Fix and re-verify.** For any mismatch vs the spec, edit the relevant component/theme file, let Vite hot-reload, and re-run the affected steps. Re-run `pnpm test && pnpm build` after any code change.

- [ ] **Step 8: Stop the dev server** (terminate the background process) and commit any fixes.

```bash
git add -A
git commit -m "fix(web): control panel adjustments from playwright verification"
```

---

## Self-Review Notes

- **Spec coverage:** theme (T1) · types/endpoints (T2) · harness state (T3) · delegated-run state (T4) · handlers+scopes+rail (T5) · harness list incl. login icon + greyed auth (T6) · delegated feed incl. Stop + empty state (T7) · layout B + lifecycle header w/ start-stop + conn dots (T8) · cleanup + CLAUDE.md (T9) · Playwright verify (T10). All spec sections mapped.
- **Backend untouched:** no Python files modified — matches mock-only scope.
- **Type consistency:** `HarnessStatus`/`DelegatedRun` field names and `DelegatedRunStatus` values are used identically across Tasks 2-8; mock `NotFoundError` codes (`HARNESS_NOT_FOUND`, `DELEGATED_RUN_NOT_FOUND`) match between state modules and handlers.
- **Assertion style:** tests avoid `jest-dom` matchers (not configured) — truthiness + DOM props only.
- **Open risk flagged inline:** `loadError` signature is verified in T8 Step 2 before relying on it.
