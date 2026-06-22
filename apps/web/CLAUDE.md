# apps/web — Frontend (React + Vite + TS + Tailwind)

A separate client over the Control Plane's `/api/v1`, not part of it. Always call the backend
via the relative `/api/v1/...` path (Vite proxies it in dev; same-origin in the container) —
never hardcode `http://localhost:8000`. Read the root `CONTEXT.md` for domain terms.

`pnpm install`; `pnpm dev` (`:5173`); `pnpm test` (vitest); `pnpm build` (tsc + vite);
`pnpm e2e` (Playwright, specs in `e2e/`, runs against `pnpm dev:mock`).

Devcontainer `status` and harness install/auth status are **live** (computed by the backend, never persisted): the status union has no `created` (a never-started devcontainer is `stopped`). The harness panel shows a "Runtime not connected" message when the runtime is disconnected (`HarnessStatusList.known === false`). Devcontainers carry a `source` (`manual` | `discovered`). The detail view's top bar carries lifecycle icon controls (Start/Stop, and Remove-container with confirm — kills+removes the container via `removeContainer`/`POST .../remove-container` but keeps the devcontainer in the list, unlike the list page's trash which `DELETE`s the record). Runtime lives in its own "Runtime" section below (above Coding harnesses): a three-state indicator (`dc.runtime.state` — `connected` green / `launching` accent / `disconnected` grey), a "Logs" button that opens a dialog **streaming** the runtime log live (chunked-fetch + `AbortController`; a live/ended indicator), and a control that is **Stop runtime** (`stop-runtime`) when connected or **Inject** (greyed/disabled unless the container is running) otherwise; the install/authenticate spinner persists until the SSE-driven status update flips the flag.

## Where things live

- `index.html`, `src/main.tsx` — entry; mounts the router.
- `src/index.css` — Tailwind + global styles.
- `src/routes/` — pages and routing.
  - `router.tsx` — route table (`/devcontainers`, `/devcontainers/:id`, `/settings`).
  - `AppShell.tsx` — layout wrapper (sidebar + rails + outlet).
  - `Devcontainers.tsx`, `DevcontainerDetail.tsx`, `Settings.tsx` — one per route.
- `src/components/` — shared UI: `Sidebar`, `PageHeader`, `EmptyState`, `RailActivity`, `RailBackend`. `RailActivity` is the right-rail panel; scoped to the open devcontainer detail route, it lists that devcontainer's active (running) delegated runs (name · harness · model) and renders nothing elsewhere.
- `src/lib/api/` — the only place that talks to the backend.
  - `client.ts` — fetch wrapper + `ApiError`. `endpoints.ts` — typed endpoint functions. `useApiQuery.ts` — React data-fetching hook. `types.ts` — API DTOs. `index.ts` — barrel.
- `src/lib/cn.ts` — `clsx` + `tailwind-merge` className helper.
- `src/mock/` — Control Plane API Mocking. `handlers.ts` — MSW request handlers (wildcard origin, browser + Node). `fixtures.ts` — healthy baseline DTOs for static read endpoints. `state/` — mutable in-browser stores (devcontainers, `state/harnesses.ts`, `state/delegatedRuns.ts`) seeded from fixed data; handlers mutate these so user actions persist across refetches. `state/seeds.ts` holds shared seed identities so a devcontainer id means the same object across stores and fixtures. `scenario.ts` / `useScenario.ts` — 6-scenario global store (localStorage-persisted). `events.ts` / `useMockSse.ts` — `MockEventSource` adapter replacing browser `EventSource` for `/api/v1/events`; `emitInvalidation(scope)` and `setStreamState(...)` drive the SWR refetch path. Scopes: `devcontainers`, `runtime`, `harnesses`, `delegated_runs`. Harness endpoints: `/harnesses`, `/harnesses/:name/install`, `/harnesses/:name/authenticate`. Delegated-run endpoint: `/delegated-runs` (list). Runtime endpoints: `stop-runtime` (POST), `runtime-logs/stream` (GET, chunked `ReadableStream`). `browser.ts` — `setupWorker`. `RailMock.tsx` — right-rail controls (scenario indicator + stream state + scope-emit buttons). `src/routes/MockScenarios.tsx` — dev-only `/mock` route with full scenario + event stream controls. Active only when `VITE_API_MOCKING=true` (`pnpm dev:mock`); tests use `msw/node` with the same handlers. See `src/mock/README.md` for maintenance detail.
- `vite.config.ts` — dev server + `/api/v1` proxy. `vitest.config.ts`, `eslint.config.js`, `tsconfig*.json` — tooling.

## Conventions

- All backend access goes through `src/lib/api/` — components import from there, never `fetch` directly.
- New API call ⇒ add to `endpoints.ts` + `types.ts`; keep DTO types in sync with the backend's Pydantic schemas.
- New or changed frontend API usage ⇒ update Control Plane API Mocking in the same change: handlers for new endpoints, fixtures for UI-used DTO fields, mutable mock state for user actions that should affect later refetches, and manual invalidation controls for live-update behavior humans need to inspect. Do not mock backend behavior the UI does not expose.
- Compose classNames with `cn(...)`.
