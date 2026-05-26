# VIB-8 — Frontend shell and navigation

## Context

Vibing is a local operations center for AI coding agents. The MVP is a single-user, local-only React + Vite + TypeScript frontend backed by a FastAPI + SQLite service.

Until now the frontend is a single `App.tsx` that fetches `/api/v1/health` and renders a status card (`apps/web/src/App.tsx`). VIB-8 introduces the persistent shell every later MVP ticket will plug into.

## Goal

Ship the app shell, navigation, five route placeholders, and live backend status — sized strictly to the ticket's acceptance criteria.

## Acceptance criteria (from VIB-8)

- App shell exists.
- Routes exist for Workspace List, Workspace Detail, Agent Inbox, Approval Queue, and Settings.
- Navigation is visible.
- Empty states are shown for each screen.
- Frontend can load basic backend health/config data.

## Visual direction

Professional, modern, minimal, flat colours. Light mode only.

### Palette — Warm Zinc + Amber

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#ffffff` | Page background, main content area |
| `--surface-sidebar` | `#f6f5f3` | Sidebar background |
| `--surface-rail` | `#fafaf9` | Activity rail background |
| `--surface-muted` | `#f4f1eb` | Empty-state icon background |
| `--border` | `#e7e5e0` | Hairlines between regions |
| `--text` | `#1c1917` | Headings, primary text |
| `--text-muted` | `#78716c` | Body, nav items |
| `--text-subtle` | `#a8a29e` | Empty placeholder lines, metadata |
| `--accent` | `#d97706` | Active nav border, link, focus ring |
| `--accent-bg` | `#fdf4e3` | Active nav item background |
| `--ok` | `#16a34a` | Backend status dot when healthy |
| `--bad` | `#dc2626` | Backend status dot when unreachable |

Palette is exposed via Tailwind's `@theme` block (Tailwind v4) so utilities like `bg-surface-sidebar` and `text-accent` work directly.

### Layout

Three-column shell that fills the viewport:

- **Sidebar** (200 px, `--surface-sidebar`): brand wordmark "Vibing" + four nav items (Workspaces, Inbox, Approvals, Settings). Active item gets the amber left border + `--accent-bg` background. No count badges in VIB-8 — they appear in later tickets once Inbox/Approvals have real data.
- **Main** (flex 1, `--bg`): per-route header (route title + small crumbs line) + body. The empty-state block centers in the body.
- **Activity rail** (240 px, `--surface-rail`): two panels stacked. **Activity** at the top, **Backend** at the bottom (separated by `flex-grow` spacer).

### Empty state

Reusable `<EmptyState>` block: small rounded icon (40 × 40, `--surface-muted` background, amber-tinted SVG), bold 15 px headline, one-sentence helper paragraph (max-width ~320 px, `--text-muted`). No CTA buttons in VIB-8.

### Per-page empty-state copy

| Route | Path | Headline | Helper |
|---|---|---|---|
| Workspaces | `/workspaces` | No workspaces yet | Your isolated development environments will appear here. |
| Workspace Detail | `/workspaces/:id` | Workspace not found | This workspace doesn't exist or hasn't been created yet. |
| Inbox | `/inbox` | Inbox is empty | Questions, approval requests, failures and completions from your agent sessions will appear here. |
| Approvals | `/approvals` | No pending approvals | Actions Claude Code asks permission for will queue here for your decision. |
| Settings | `/settings` | Settings coming soon | Preferences for Vibing will live here. |

## Architecture

### Dependencies to add (`apps/web/package.json`)

Runtime:

- `react-router` (v7, library mode)
- `tailwindcss` (v4)
- `@tailwindcss/vite`
- `clsx`
- `tailwind-merge`
- `class-variance-authority`

No state-management library, no data-fetching library, no icon library, no animation library, no shadcn primitives copied in. SVG icons are inlined per use; the count is small (4 nav + 5 empty-state + a chevron, give or take).

### File layout (`apps/web/src/`)

```
main.tsx               # mounts <RouterProvider router={router} />
index.css              # @import "tailwindcss"; CSS-var palette under @theme
lib/
  cn.ts                # cn(...inputs) = twMerge(clsx(inputs))
  api.ts               # fetchHealth(), fetchConfig() — typed fetch wrappers
routes/
  router.tsx           # createBrowserRouter([...])
  AppShell.tsx         # sidebar + <Outlet /> + rail
  Workspaces.tsx
  WorkspaceDetail.tsx
  Inbox.tsx
  Approvals.tsx
  Settings.tsx
components/
  Sidebar.tsx
  RailBackend.tsx      # fetches /health + /config once on mount
  RailActivity.tsx     # static "No active agents yet." for VIB-8
  EmptyState.tsx       # icon + headline + helper
  PageHeader.tsx       # title + crumbs
```

The existing `App.tsx` and `App.css` are deleted (their contents are absorbed into the new structure). The existing `index.css` is replaced with the Tailwind-based one.

### Routing

`createBrowserRouter` with a single root layout route:

```ts
[
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, loader: () => redirect("/workspaces") },
      { path: "workspaces", element: <Workspaces /> },
      { path: "workspaces/:id", element: <WorkspaceDetail /> },
      { path: "inbox", element: <Inbox /> },
      { path: "approvals", element: <Approvals /> },
      { path: "settings", element: <Settings /> },
      { path: "*", loader: () => redirect("/workspaces") },
    ],
  },
]
```

`WorkspaceDetail` for VIB-8 always shows the "Workspace not found" empty state since no list exists to navigate from. The route exists so links from later tickets resolve cleanly.

### Backend status (the only live data)

`RailBackend.tsx`:

- On mount, calls `fetchHealth()` and `fetchConfig()` in parallel.
- If both succeed: green dot (`--ok`) + `service: <app_name from /config>` + `api: <api_v1_prefix from /config>`.
- If either fails: red dot (`--bad`) + `service: unavailable` + the api line hidden.
- No retry, no toast, no polling — a manual page reload is the recovery.

`lib/api.ts` exports two typed functions that hit `/api/v1/health` and `/api/v1/config`. Both throw on non-OK responses. The shapes mirror the Pydantic models in `apps/api/src/vibing_api/api/routes/{health,config}.py`.

### Vite / TS / lint config

- `vite.config.ts` adds the `@tailwindcss/vite` plugin alongside the existing `react()` plugin. Proxy config is unchanged.
- `tsconfig.app.json` is unchanged.
- `eslint.config.js` is unchanged.

## Out of scope

Deliberately not in VIB-8:

- Workspace list/detail wiring to `/api/v1/workspaces`.
- Any create/update/delete UI.
- Inbox, Approvals, or Settings functionality.
- Dark mode and a theme toggle.
- Agent activity in the rail (only the empty-state line in VIB-8).
- Toasts, notifications, sound, badges with real counts.
- Tests beyond what TypeScript and `pnpm build` enforce — the shell has no logic to test. If logic appears (it shouldn't), it gets a test.
- Storybook, component docs, design tokens beyond the palette table above.

## Risks and watchouts

- **Tailwind v4 setup is different from v3.** Uses the `@tailwindcss/vite` plugin and `@import "tailwindcss";` in CSS — no `tailwind.config.js`, no PostCSS config. The palette goes inside `@theme { ... }` in the same CSS file.
- **Strict-mode double mount** will fire the `RailBackend` fetch twice in dev. That's fine — it's idempotent and we don't show flashing UI. Production renders once.
- **React 19** is current in the project. `react-router` v7 supports React 19; no special handling needed.
- The existing `App.tsx`/`App.css` and the current `index.css` will be removed; reviewers should expect those files to disappear, not be edited.

## Done-when checklist

- `pnpm install` succeeds with the new deps.
- `pnpm build` succeeds.
- `pnpm dev` serves the app at `http://localhost:5173`.
- Visiting `/`, `/workspaces`, `/workspaces/anything`, `/inbox`, `/approvals`, `/settings` each render the shell with the correct active nav item and the correct empty state.
- Browser back/forward and direct URL entry work.
- With the backend running, the Backend panel shows the green dot and `service: vibing-api`. With the backend stopped, it shows the red dot and `service: unavailable`.
- Visual matches the Warm Zinc + Amber palette and the layout in the brainstorm mockups (`.superpowers/brainstorm/.../content/final-shell.html`, `color-themes.html`).
