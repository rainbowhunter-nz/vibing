# apps/web — Frontend (React + Vite + TS + Tailwind)

A separate client over the Control Plane's `/api/v1`, not part of it. Always call the backend
via the relative `/api/v1/...` path (Vite proxies it in dev; same-origin in the container) —
never hardcode `http://localhost:8000`. Read the root `CONTEXT.md` for domain terms.

`pnpm install`; `pnpm dev` (`:5173`); `pnpm test` (vitest); `pnpm build` (tsc + vite).

## Where things live

- `index.html`, `src/main.tsx` — entry; mounts the router.
- `src/index.css` — Tailwind + global styles.
- `src/routes/` — pages and routing.
  - `router.tsx` — route table (`/devcontainers`, `/devcontainers/:id`, `/inbox`, `/approvals`, `/settings`).
  - `AppShell.tsx` — layout wrapper (sidebar + rails + outlet).
  - `Devcontainers.tsx`, `DevcontainerDetail.tsx`, `Inbox.tsx`, `Approvals.tsx`, `Settings.tsx` — one per route.
- `src/components/` — shared UI: `Sidebar`, `PageHeader`, `EmptyState`, `RailActivity`, `RailBackend`.
- `src/lib/api/` — the only place that talks to the backend.
  - `client.ts` — fetch wrapper + `ApiError`. `endpoints.ts` — typed endpoint functions. `useApiQuery.ts` — React data-fetching hook. `types.ts` — API DTOs. `index.ts` — barrel.
- `src/lib/cn.ts` — `clsx` + `tailwind-merge` className helper.
- `vite.config.ts` — dev server + `/api/v1` proxy. `vitest.config.ts`, `eslint.config.js`, `tsconfig*.json` — tooling.

## Conventions

- All backend access goes through `src/lib/api/` — components import from there, never `fetch` directly.
- New API call ⇒ add to `endpoints.ts` + `types.ts`; keep DTO types in sync with the backend's Pydantic schemas.
- New or changed frontend API usage ⇒ update Control Plane API Mocking in the same change: handlers for new endpoints, fixtures for UI-used DTO fields, mutable mock state for user actions that should affect later refetches, and manual invalidation controls for live-update behavior humans need to inspect. Do not mock backend behavior the UI does not expose.
- Compose classNames with `cn(...)`.
