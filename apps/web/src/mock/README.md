# Control Plane API Mocking — Maintenance Guide

**Control Plane API Mocking** ([glossary](../../../../CONTEXT.md), [ADR-0007](../../../../docs/adr/0007-control-plane-api-mocking-uses-msw-and-a-dev-eventsource-adapter.md)) is a frontend development mode where the browser receives mock `/api/v1` Control Plane HTTP responses and live invalidation events without requiring a running Control Plane. It is a **UI inspection aid** — not a substitute source of truth for Runtime Events or projections.

Start it with:

```
pnpm dev:mock   # VITE_API_MOCKING=true vite
```

## Module map

| File | Role |
|---|---|
| `handlers.ts` | Central MSW request handlers (wildcard origin — works in browser worker and `msw/node` tests) |
| `fixtures.ts` | Healthy baseline DTO values for static read endpoints |
| `state/seeds.ts` | Shared seed identities (devcontainers, agent sessions) — one id means the same object across every mock module |
| `state/devcontainers.ts` | Mutable in-browser store for devcontainer CRUD/lifecycle |
| `state/inbox.ts` | Mutable in-browser store for inbox events |
| `state/approvals.ts` | Mutable in-browser store for approval requests |
| `scenario.ts` + `useScenario.ts` | Global scenario store (6 scenarios); persisted to `localStorage` |
| `events.ts` + `useMockSse.ts` | `MockEventSource` adapter (replaces browser `EventSource` for BOTH `/api/v1/events` and the per-session `/stream`), stream-state store, `emitInvalidation`, `liveInstancesMatching` |
| `agentSessionStreams.ts` | Scripted per-session SSE delta playback (ADR-0010): plays assistant text token-by-token through the MockEventSource opened at a session's `/stream` URL. `playSessionStream(sessionId, opts)` with an injectable `schedule` for deterministic tests. Wired into RailMock as a "play live deltas" button |
| `browser.ts` | `setupWorker(...handlers)` for the service worker |
| `RailMock.tsx` | Right-rail mock controls (scenario indicator, stream state, scope-emit buttons) |
| `routes/MockScenarios.tsx` | Dev-only `/mock` route (full scenario + event stream controls) |
| `index.ts` | Barrel + `isMockMode()` |

`main.tsx` `bootstrap()` starts the MSW worker and calls `installMockEventSource()` — both inside the `VITE_API_MOCKING === 'true'` branch, before the React tree renders. The `/mock` route is added to `router.tsx` only in mock mode.

## Scenarios

Six global scenarios switch all handler responses simultaneously:

| Scenario | Effect |
|---|---|
| `happy` | Seeded baseline data (fixtures + mutable stores) |
| `empty` | List endpoints return `{ items: [] }` |
| `api-error` | 500 error envelope on every endpoint |
| `network-down` | Network-level failure (`HttpResponse.error()`) |
| `stale-action` | 409 conflict on every endpoint |
| `not-found` | 404 not-found on every endpoint |

Switch via the `/mock` route or the right-rail "switch scenario" link.

## Tests

`vitest` + `msw/node` — same `handlers` array, no browser worker needed. Each test file in `src/mock/__tests__/` and `state/__tests__/` uses `setupServer(...handlers)` and calls the relevant `reset*()` helpers in `beforeEach`.

---

## When you change a frontend API call, update…

### 1. Handlers — new or changed endpoints

**When**: a new `/api/v1/…` endpoint is added, a method changes, or a URL param changes.

**How**:

- Add an `http.<method>('*/api/v1/path', handler)` entry in `handlers.ts` and include it in the appropriate composed array (`devcontainerHandlers`, `inboxHandlers`, etc.) or directly in the `handlers` export.
- Wildcard prefix (`*/api/v1/…`) keeps the same handler valid in the browser service worker and in Node-based vitest tests.
- **Static read endpoint** (no user action mutates it): use `scenarioResponse(fixture, emptyValue?)`. Pass an empty value (e.g. `{ items: [] }`) as the second argument for list endpoints.
- **Mutable-state route** (user action should persist into later refetches): call `scenarioFailure(notFoundCode?, staleCode?)` first; if it returns non-null, return that response. Otherwise do real store logic. Use domain-specific error codes (`DEVCONTAINER_NOT_FOUND`, `INBOX_EVENT_NOT_FOUND`, `APPROVAL_REQUEST_NOT_PENDING`) for per-item routes; use the generic fallback for collection routes.
- Add a test covering at least the happy-path and one error scenario.

### 2. Fixtures — new DTO fields the UI reads

**When**: a DTO grows a new field that a screen or component actually reads (renders or passes to a hook/function).

**How**:

- Add the field to the relevant fixture in `fixtures.ts`, matching the type from `src/lib/api/types.ts`.
- Field coverage should match what the UI reads — do not add fields the UI ignores; do not omit fields the UI reads.
- Fixtures cover **static** read endpoints (health, status, config, runtimeStatus, settings, diagnostics) plus read-only `agentSessions` (seeded against dc-seed-0001; the handler filters it by devcontainer_id). For mutable domain objects, the seed data lives in `state/`.

### 3. Mutable state — user actions that should survive later refetches

**When**: a user action (create, edit, delete, start/stop, mark-read, resolve, approve/reject) should be reflected in subsequent GET responses within the same dev session.

**How**:

- Extend or add a module in `state/`. Each state module exports: a typed `NotFoundError` or `StaleError` class, a `reset*()` function (called in tests), a read function, and one or more write functions that deep-copy on read and mutate an in-memory store seeded from a fixed `SEED` array.
- Wire the handler to call the store function instead of returning a fixture. Wrap store calls in `try/catch` for `NotFoundError`/`StaleError` and return the appropriate `notFoundResponse`/error envelope.
- **Purely static reads** (health, config, diagnostics, etc.) do not need mutable state — keep them in `fixtures.ts` and `scenarioResponse`.
- Call `reset*()` in `beforeEach` for tests that exercise mutable routes.

### 4. Manual invalidation controls — live-update behavior to inspect

**When**: a new data domain needs human-driven invalidation testing (e.g. a new route that refetches on an SSE invalidation event).

**How**:

- Add the new `Scope` value to `src/lib/events/types.ts` (the shared type, not mock-specific).
- Add the scope to the `SCOPES` arrays in `RailMock.tsx` and `routes/MockScenarios.tsx` so the emit button appears in both the right-rail and the `/mock` page.
- Emitting a scope nudges the existing stale-while-revalidate refetch path (`useApiQuery` + the SSE coordinator) — it does **not** mutate stores or simulate any backend logic.
- Stream-state controls (`connected` / `reconnecting` / `disconnected`) are already in both places; add a new connection scenario only if the coordinator grows a new state that needs visual inspection.

### 5. Per-session live stream — token-by-token assistant text to inspect

**When**: a session's live turn-deltas (ADR-0010) need human inspection without a real Control Plane.

**How**:

- The per-session stream is a SEPARATE `EventSource` (`openAgentSessionStream`) from the global invalidation coordinator. `installMockEventSource()` swaps `globalThis.EventSource` for ALL EventSources, so per-session streams become `MockEventSource` instances too (keyed by their `/stream` URL).
- `agentSessionStreams.ts` holds scripted text-delta scripts per session id. `playSessionStream(sessionId)` delivers `run_started` → text tokens → `run_ended` as named `turn_delta` events to the matching live instance(s), mirroring the real wire format.
- The RailMock "play live deltas" button plays the default script for a seeded active session (`as-seed-0005`). To inspect: open that session's chat while the devcontainer is running, then click play — assistant text types in token-by-token and reconciles to the transcript on `run_ended`.
- Boundary: this is scripted playback only — no Runtime Event simulation or projection logic.

---

## Manual verification procedure (AC6)

Run once after any significant change to the mock subsystem. Automated checks (`pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm build`) are the machine-checked baseline; this procedure adds human confirmation.

1. **Boot** — `pnpm dev:mock` in `apps/web`. Confirm the browser console shows `[MSW] Mocking enabled.` and no console errors on load.
2. **Scenario route** — navigate to `/mock`. Confirm 6 scenario buttons (happy/empty/api-error/network-down/stale-action/not-found) and the Event Stream section (3 connection-state buttons + 5 scope-emit buttons) render.
3. **Right-rail controls** — load `/devcontainers`. Confirm the right rail shows the Mock section: current scenario name, "switch scenario" link, stream-state dot + label, stream-state buttons, and scope-emit buttons.
4. **Happy scenario** — select `happy` on `/mock`. Load `/devcontainers` — seeded items render (my-webapp, api-service, data-pipeline, legacy-app). Load `/inbox` — 4 seeded events render.
5. **Empty scenario** — select `empty`. Reload `/devcontainers` and `/inbox` — both show empty-state UI (no items).
6. **Error scenario** — select `api-error`. Reload `/devcontainers` — the page shows an error state (not a list).
7. **Manual invalidation** — switch back to `happy`. On `/devcontainers`, click the `devcontainers` scope-emit button in the right rail; confirm the list refetches (a brief loading state or unchanged seeded data confirms the path ran without error). No store mutation is expected — emits nudge SWR only.
8. **Stream state** — click `disconnected` in the right rail. Confirm the stream-health indicator updates. Click `connected` to restore.

## Boundary: what must not be modelled

Control Plane API Mocking **must not model backend behavior the UI does not expose**. Specifically:

- No Runtime simulation — `MockEventSource` emits invalidation nudges only; it does not simulate Runtime Event processing, projection updates, or workflow logic.
- No Control Plane projection logic — mock stores are flat CRUD; they do not replicate event-sourcing, cascades, or derived state the backend computes.
- No automatic playback — scenarios and invalidation events are always manually triggered.
- No Storybook integration or toast system.
- **No cross-store cascades.** Resolving an approval mutates only the approvals store; the inbox event that references it keeps its embedded snapshot and unread status until refetched against the real backend. The UI's post-action "awaiting runtime…" state stands in for the cascade the real Control Plane would project.
- **`empty` scenario only empties list endpoints.** Per-item routes (`/devcontainers/:id`, `/agent-sessions`) still return seeded data in `empty` — there is no UI path to them when the list is empty, so this is intentional.

If a screen does not read a field, do not add it to fixtures. If the UI does not surface a state transition, do not add it to the mock stores.
