# VIB-14 — Frontend API client foundation

## Context

Vibing's frontend (`apps/web`, React 19 + Vite + TypeScript + Tailwind 4) currently keeps all backend calls in a single file: `apps/web/src/lib/api.ts`. It exports a `getJson<T>(path)` helper plus five typed `fetch*` functions (health, config, workspaces, settings, diagnostics — `status` is missing). Three page-level consumers (`Workspaces.tsx`, `Settings.tsx`, `RailBackend.tsx`) reinvent the same `{loading | ready | error}` discriminated-union state machine with a `useEffect` + `cancelled` flag.

Two gaps make this fragile as more endpoints land:

- **Errors are opaque.** `getJson` throws `new Error(\`${path} ${status}\`)`. The backend already speaks a standard envelope (`apps/api/src/vibing_api/core/errors.py`):
  ```json
  { "error": { "code": "WORKSPACE_NOT_FOUND", "message": "...", "details": null } }
  ```
  No consumer can recover the `code` or render the `message`.
- **Loading/cancellation boilerplate is copy-pasted.** Every screen hand-rolls the same hook; one bad copy and the page leaks `setState` after unmount under React strict-mode.

VIB-14 establishes a small, durable foundation: a split client module, a typed error contract, a hook that owns the loading/cancellation pattern, and the first real frontend tests in the repo.

## Goal

Promote `lib/api.ts` into a small `lib/api/` module with:
- typed response shapes for **every** existing v1 endpoint (workspace, config, status, diagnostics, plus health and settings),
- a parsed-envelope error contract (`ApiError` / `NetworkError`),
- a `useApiQuery` hook that captures the loading / cancellation pattern,
- a `sendJson` write helper plus one example mutation (`deleteWorkspace`) to prove the path,
- Vitest-driven tests for success and failure paths,
- a short README documenting how new screens should consume the client.

Existing pages are **not** migrated in this ticket — they keep working through the index barrel re-exports.

## Acceptance criteria (from VIB-14)

| Criterion | Treatment this ticket |
|---|---|
| Frontend API calls are centralized behind a small client module | `lib/api/` folder; pages keep importing from `'../lib/api'` via barrel |
| Uses `/api/v1` route prefix, no hardcoded backend host | `client.ts` owns `API_BASE = '/api/v1'`; endpoint functions pass paths like `/workspaces` |
| Workspace / config / status / diagnostics response shapes typed | All present in `types.ts`; `StatusResponse` is new (rest moved from current `api.ts`) |
| Common request, loading, and error handling patterns are documented | `lib/api/README.md`; `useApiQuery` hook + manual `useEffect` pattern both covered |
| Basic tests or mocks exist for successful and failed API responses | Vitest + happy-dom; `client.test.ts` covers envelope parsing on success and four failure modes; `useApiQuery.test.tsx` covers loading/ready/error/refetch/cancellation |

## Module layout

```
apps/web/src/lib/api/
  client.ts             # API_BASE, ApiError, NetworkError, getJson, sendJson
  types.ts              # all request/response shapes
  endpoints.ts          # fetchHealth / fetchStatus / fetchConfig / fetchWorkspaces
                        # fetchSettings / fetchDiagnostics / deleteWorkspace
  useApiQuery.ts        # {loading|ready|error} hook + refetch + cancellation
  index.ts              # barrel: re-exports everything from the four files
  README.md             # pattern doc (see “Documentation” below)
  __tests__/
    client.test.ts
    useApiQuery.test.tsx
```

The existing `apps/web/src/lib/api.ts` file is deleted; `apps/web/src/lib/api/index.ts` replaces it, so `import { fetchWorkspaces, type Workspace } from '../lib/api'` continues to resolve unchanged across `Workspaces.tsx`, `Settings.tsx`, and `RailBackend.tsx`.

### Why split now

The `lib/` folder has only two other files (`cn.ts`, and shortly this module). The split is cheap and pre-empts the next 5–10 endpoints (sessions, inbox, approvals) from re-bloating a single file. Each new file stays focused enough to read in one screen.

## Types (`types.ts`)

Carry across the existing interfaces verbatim — they already match the backend models — and add the two missing ones.

```ts
// --- existing, moved from lib/api.ts unchanged ---
export interface HealthResponse  { status: string; service: string }
export interface ConfigResponse  { app_name: string; api_v1_prefix: string }

export interface Workspace {
  id: string
  name: string
  local_path: string
  status: string
  created_at: string
  updated_at: string
}
export interface WorkspaceList { items: Workspace[] }

export interface RuntimeDetection {
  docker: boolean | null
  podman: boolean | null
  devcontainer_cli: boolean | null
  claude_code: boolean | null
}
export interface SettingsResponse {
  backend_host: string
  backend_port: number
  runtime: RuntimeDetection
}

export type DiagnosticStatus = 'ok' | 'fail' | 'unknown'
export interface DiagnosticCheck {
  id: string
  label: string
  status: DiagnosticStatus
  message: string | null
}
export interface DiagnosticsResponse { checks: DiagnosticCheck[] }

// --- new ---
export interface StatusResponse {
  status: string
  service: string
  version: string
}

export interface ApiErrorBody { code: string; message: string; details: unknown }
export interface ApiErrorEnvelope { error: ApiErrorBody }
```

`SettingsResponse` deliberately matches the **current** backend shape (`apps/api/src/vibing_api/api/routes/settings.py`: `backend_host`, `backend_port`, `runtime`). The fuller shape in the VIB-10 spec (`workspace_storage_location`, `editor_preference`, `notifications_enabled`) was not implemented yet, and is not in scope here.

## Client + error contract (`client.ts`)

```ts
const API_BASE = '/api/v1'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'NetworkError'
  }
}

export async function getJson<T>(path: string): Promise<T>
export async function sendJson<T>(
  path: string,
  method: 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<T | void>
```

**Behaviour contract:**

- `path` is appended to `API_BASE`. Callers pass `'/workspaces'`, never `'/api/v1/workspaces'`. Removes the one repeated string in every helper today.
- Both helpers send `Accept: application/json`. `sendJson` adds `Content-Type: application/json` when `body !== undefined`, and JSON-serializes the body.
- On 2xx with a JSON body → resolves the parsed body, typed as `T`.
- On 204 (no content) → `sendJson` resolves `undefined`. (No GET endpoint returns 204 today, so `getJson` does not handle that case.)
- On non-2xx:
  - Try to parse the body as the envelope `{error: {code, message, details}}` → throw `ApiError(status, code, message, details)`.
  - If parsing fails (empty body, non-JSON, missing `error` key) → throw `ApiError(status, 'HTTP_ERROR', response.statusText || \`HTTP ${status}\`)`.
- On `fetch` rejection (network down, DNS failure, CORS) → throw `NetworkError(originalError.message)`.

The two error classes deliberately extend `Error` (not a discriminated union) so existing `.catch(() => setState({kind: 'error'}))` keeps compiling unchanged. Callers that want detail use `instanceof ApiError`.

## Endpoints (`endpoints.ts`)

```ts
import { getJson, sendJson } from './client'
import type {
  HealthResponse, StatusResponse, ConfigResponse,
  WorkspaceList, SettingsResponse, DiagnosticsResponse,
} from './types'

export const fetchHealth      = () => getJson<HealthResponse>('/health')
export const fetchStatus      = () => getJson<StatusResponse>('/status')
export const fetchConfig      = () => getJson<ConfigResponse>('/config')
export const fetchWorkspaces  = () => getJson<WorkspaceList>('/workspaces')
export const fetchSettings    = () => getJson<SettingsResponse>('/settings')
export const fetchDiagnostics = () => getJson<DiagnosticsResponse>('/diagnostics')

export const deleteWorkspace  = (id: string) =>
  sendJson<void>(`/workspaces/${encodeURIComponent(id)}`, 'DELETE')
```

`deleteWorkspace` is the one example mutation — it proves the `sendJson` path end-to-end. No UI consumes it yet (the trash button in `Workspaces.tsx` is purely cosmetic). POST/PATCH wrappers land alongside their first caller in later tickets.

## `useApiQuery` hook (`useApiQuery.ts`)

```ts
export type QueryState<T> =
  | { kind: 'loading' }
  | { kind: 'ready'; data: T }
  | { kind: 'error'; error: ApiError | NetworkError | Error }

export interface QueryResult<T> {
  state: QueryState<T>
  refetch: () => void
}

export function useApiQuery<T>(fn: () => Promise<T>, deps: unknown[]): QueryResult<T>
```

Internally:
- Tracks `state` via `useState<QueryState<T>>`, starts as `{kind: 'loading'}`.
- A `refetchToken` counter (`useState(0)`) drives a `refetch()` that simply increments it.
- `useEffect([...deps, refetchToken])` runs `fn()`; a local `cancelled` flag guards the resolve/reject paths so a torn-down render (React strict-mode double-mount, dep change, unmount) doesn't `setState` on a dead component. Same shape `Workspaces.tsx` uses today, hoisted into one place.
- Each `refetch()` resets state to `{kind: 'loading'}` before the fetch fires (so consumers can show the spinner again).
- Errors are caught and stored on the state object. The hook does not throw.

**Why the deps array is required** rather than letting the hook diff `fn`: callers typically pass an arrow (`() => fetchWorkspace(id)`) that changes identity every render. Forcing an explicit deps array mirrors `useEffect` and matches what consumers already think about. ESLint's `react-hooks/exhaustive-deps` won't lint a custom hook out of the box; the README notes this and the trade-off.

**Existing pages are not migrated.** This is a foundation ticket: they keep their inlined state machines and continue importing the typed `fetch*` functions through `lib/api`'s barrel. A follow-up ticket can adopt the hook page-by-page.

## Documentation (`lib/api/README.md`)

One screen of text covering:

1. **Base URL & proxy.** Vite proxies `/api/v1/*` → `http://localhost:8000` (see `apps/web/vite.config.ts`). Production serves API + bundle from one origin (see `apps/api/src/vibing_api/main.py`). Either way the relative path works — **never hardcode `http://localhost:8000`**.
2. **Calling endpoints.** Import named functions from `'../lib/api'`. Each returns parsed JSON or throws `ApiError` / `NetworkError`.
3. **Pattern A — `useApiQuery`** for new screens. Single example showing `const {state, refetch} = useApiQuery(fetchWorkspaces, [])` plus the `state.kind` switch.
4. **Pattern B — manual `useEffect` + `cancelled` flag**, kept here for reference because the existing pages still use it; link to `Workspaces.tsx` as the canonical example.
5. **Error handling.** `if (err instanceof ApiError)` to inspect `err.code` (e.g. `WORKSPACE_NOT_FOUND`) and `err.message`. Otherwise fall back to a generic "Something went wrong" string.
6. **Adding an endpoint** — 3-step checklist: (a) add the type to `types.ts`, (b) add the function to `endpoints.ts`, (c) it's automatically re-exported via `index.ts`.
7. **Mocking in tests** — point at `__tests__/client.test.ts` as the worked example (stubbing `globalThis.fetch`).

## Tests

### Tooling

Add the following dev dependencies to `apps/web/package.json` (via `pnpm add -D`):

- `vitest`
- `happy-dom`
- `@testing-library/react`
- `@testing-library/dom` (peer of testing-library/react)

Add a `test` script:

```json
"test": "vitest run",
"test:watch": "vitest"
```

Add `apps/web/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'happy-dom',
    globals: false,
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
```

`globals: false` keeps `describe`/`it`/`expect` as explicit imports — matches the project's preference for explicit syntax.

Vitest picks up `tsconfig.app.json` paths automatically via the Vite plugin chain, so no separate tsconfig is needed.

### `client.test.ts`

Stubs `globalThis.fetch` per test (`vi.stubGlobal('fetch', ...)`), restores in `afterEach`. Covers:

| Case | Expectation |
|---|---|
| `getJson` 200 with JSON body | resolves the parsed body |
| `getJson` 404 with envelope `{error: {code: 'WORKSPACE_NOT_FOUND', ...}}` | throws `ApiError` with matching `status`, `code`, `message` |
| `getJson` 422 with envelope + `details` array | throws `ApiError` with `details` preserved |
| `getJson` 500 with non-envelope body (`<html>...`) | throws `ApiError(500, 'HTTP_ERROR', ...)` |
| `getJson` fetch rejects | throws `NetworkError` with the underlying message |
| `sendJson` 'PATCH' with body | sends correct method, `Content-Type`, serialized body; resolves parsed response |
| `sendJson` 'DELETE' returning 204 | resolves `undefined` |
| Both helpers | prepend `/api/v1` to the path |

### `useApiQuery.test.tsx`

Uses `@testing-library/react`'s `renderHook` + `act`. Covers:

| Case | Expectation |
|---|---|
| Resolving function | state transitions `loading` → `ready` with `data` |
| Rejecting with `ApiError` | state transitions `loading` → `error` with the same `ApiError` reference |
| `refetch()` after success | state flips back to `loading`, then resolves again |
| Hook unmount before promise settles | no warning; subsequent resolve does not throw or call `setState` |

The cancellation test relies on a deferred promise (created manually in-test) so we control when it resolves.

## Implementation order (sequencing)

1. Add `vitest` + `happy-dom` + `@testing-library/react` + `vitest.config.ts`, add `test` script. Confirm `pnpm test` runs zero tests cleanly.
2. Create `lib/api/types.ts` (move existing interfaces verbatim + add `StatusResponse`, `ApiErrorBody`, `ApiErrorEnvelope`).
3. Create `lib/api/client.ts` (`API_BASE`, `ApiError`, `NetworkError`, `getJson`, `sendJson`). Add `__tests__/client.test.ts` first (red), then implement until green.
4. Create `lib/api/endpoints.ts` (the seven functions). Smoke-import in the test file to confirm types compile.
5. Create `lib/api/useApiQuery.ts` and `__tests__/useApiQuery.test.tsx`. Red → green.
6. Create `lib/api/index.ts` barrel re-exporting from `types.ts`, `client.ts`, `endpoints.ts`, `useApiQuery.ts`.
7. Delete `apps/web/src/lib/api.ts`. `pnpm build` should pass with no changes to any consumer; `pnpm test` should pass.
8. Write `lib/api/README.md`.

## Out of scope (explicit)

- **No migration** of `Workspaces.tsx`, `Settings.tsx`, or `RailBackend.tsx` to `useApiQuery`. They keep working through the barrel re-exports; a future ticket adopts the hook.
- **No POST/PATCH wrappers** beyond `deleteWorkspace` as the worked example. Add them alongside their first caller (e.g. when a "create workspace" form lands).
- **No streaming / SSE / WebSocket** helpers — runtime session streaming is an explicit non-goal of VIB-14.
- **No workspace start / stop actions** — explicit non-goal.
- **No inbox / approval workflow types** — explicit non-goal.
- **No retry, backoff, request-cancellation token, auth, or CSRF** — local-only single-user app.
- **No React Query / SWR / MSW** — vanilla fetch with the typed wrappers is enough for the current surface.

## Risks and watchouts

- **Test runner is new in the repo.** `pnpm test` becomes a real signal; make sure it's wired so CI (when it exists) picks it up. Today it's run-on-demand.
- **`@testing-library/react`'s `renderHook`** moved out of `react-hooks-testing-library` and into the main package in RTL v13+. Pin a current version; older docs/examples will mislead.
- **Strict-mode double mount** still fires `useApiQuery`'s effect twice in dev — the test verifying "unmount cancels" is what proves the guard works.
- **Barrel import order.** `index.ts` must re-export `types.ts` *before* `client.ts` if `client.ts` ever re-uses a type by value (currently it doesn't, but worth noting). Use type-only re-exports (`export type * from './types'`) to avoid runtime cycles.
- **Naming collision** with `ApiError`. The backend's Python class is `APIError`; the frontend's is `ApiError`. Different runtimes, no actual collision, but reviewers should expect both names in the spec.
- **Settings shape drift.** Backend currently returns the slim `{backend_host, backend_port, runtime}`; the VIB-10 design doc described a richer shape that wasn't fully implemented. We deliberately mirror **what the backend returns today** — if VIB-10 is expanded later, that ticket updates `types.ts`.

## Done-when checklist

- `apps/web/src/lib/api.ts` is deleted; `apps/web/src/lib/api/` exists with the six files above plus `__tests__/`.
- `pnpm install` clean (lockfile updated, committed).
- `pnpm build` passes (TypeScript clean, all five consumers compile unchanged).
- `pnpm test` passes (`client.test.ts` + `useApiQuery.test.tsx` green).
- Manually loading the dev app shows the same behaviour as today: Workspaces list loads, Settings page loads, the right-rail backend pill shows "Connected".
- `lib/api/README.md` documents both patterns and the add-an-endpoint checklist.
- No file outside `apps/web/src/lib/api/` and `apps/web/{package.json,pnpm-lock.yaml,vitest.config.ts}` is modified.
