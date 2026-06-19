# Devcontainer Detail → Runtime Control Panel

**Date:** 2026-06-19
**Status:** Approved (design)

## Problem

The devcontainer detail page is built around a chat interface to the main coding
harness (Claude Code). The project scope changed: users now run Claude Code
directly inside the devcontainer, so the web chat is obsolete.

The detail page should become the tool's most useful page — a **control panel and
status viewer for the devcontainer runtime**: lifecycle, runtime connectivity,
coding-harness readiness (installed/authenticated), and introspection of the
unattended work the runtime is doing (delegated runs).

## Scope

Mock-only: rebuild the page UI and mock all new endpoints via MSW + mutable state
+ scenarios. New REST endpoints are NOT implemented on the backend in this change;
their contract is documented here for later work. The whole app is re-themed dark.

Out of scope: backend REST endpoints, backend agent-session routes (left intact),
the authenticate credential-blob flow.

## Theme (whole app, dark-only)

Centralized in `apps/web/src/index.css` `@theme` tokens — slate + green. No
light/dark toggle.

| Token | Value | Use |
| --- | --- | --- |
| `--color-bg` | `#15151c` | page background |
| `--color-surface-sidebar` | `#1b1b24` | sidebar |
| `--color-surface-rail` | `#1b1b24` | rails / headers |
| `--color-surface-muted` | `#23232f` | cards, rows, hover |
| `--color-border` | `#30303f` | borders |
| `--color-text` | `#f4f4f6` | primary text |
| `--color-text-muted` | `#9a9aa8` | secondary text |
| `--color-text-subtle` | `#7c7c8a` | labels |
| `--color-accent` | `#3ddc84` | accent / primary action |
| `--color-accent-bg` | `#3ddc8422` | accent tint (badges, selection) |
| `--color-ok` | `#3ddc84` | healthy/connected |
| `--color-bad` | `#f87171` | failure |

Hardcoded Tailwind palette classes in `Devcontainers.tsx` and the rebuilt
`DevcontainerDetail.tsx` (`bg-emerald-100`, `text-emerald-800`, `bg-red-100`,
`text-red-...`) are remapped to semantic tokens (`bg-accent-bg`/`text-accent`,
`text-bad`) so every route is coherent with the dark theme. Sweep all routes and
shared components for stray light-mode literals.

## Layout

Full-width **lifecycle header** on top. Below it, two columns:
- **left:** harness list
- **right:** delegated-runs feed

Single page, no chat, no session sidebar.

### Lifecycle header

- Devcontainer name + status badge.
- Start / Stop controls (reuse existing `POST .../start`, `POST .../stop`).
  No restart.
- `worker_connected` and `agent_connected` shown as labeled dot indicators
  (green when connected, muted when not). Both already on `DevcontainerView.runtime`.
- Optional collapsible details (local path, created/updated) — carry over the
  existing `DevcontainerInfo` affordance.

### Harness list (left column)

Row per harness, two centered status columns: **Installed**, **Authenticated**.

- Green tick (`--color-accent`) = installed / authenticated.
- White **download** icon = install action (when not installed).
- White **login** icon = authenticate action (when installed, not authenticated).
- Authenticate icon greyed/disabled until the harness is installed.
- No credential flow: clicking install/authenticate calls the mock endpoint
  directly, which flips the corresponding flag. (Real backend will later wire the
  authenticate blob; the icon stays the same.)

### Delegated-runs feed (right column)

Read-only row per run, newest first:
- `run-id` (mono) + status badge (`running` / `completed` / `failed` / `stopped`).
- `harness · model · age`.
- Expandable result (completed) or error (failed).
- Live dot on `running` rows.
- **Stop** button on `running` rows → `POST .../delegated-runs/{run_id}/stop`.
- Quiet empty state when there are no runs:
  "No delegated runs — the harness will list them here when it spawns one."

## API contract (documented; mocked now, backend later)

All under `/api/v1/devcontainers/{id}`.

### Harnesses

```
GET  /harnesses
  → { items: [{ name: string, installed: bool, authenticated: bool }] }

POST /harnesses/{name}/install
  → { name, installed: true, authenticated }

POST /harnesses/{name}/authenticate          # no body for now
  → { name, installed, authenticated: true }
```

Backed by the runtime's `HarnessManager.list_statuses()` / `authenticate()`
(ADR-0012) and the harness adapters' `install()`. Maps to `HarnessStatus`
(`name`, `installed`, `authenticated`).

### Delegated runs

```
GET  /delegated-runs
  → { items: [{
        run_id: string, harness: string, model: string,
        status: "running"|"completed"|"failed"|"stopped",
        result: string | null, error: object | null,
        started_at: string
      }] }

POST /delegated-runs/{run_id}/stop
  → { run_id, status }
```

Backed by `DelegatedRunManager` (ADR-0013) `get_result` / `stop`. `started_at` is
new vs the in-memory `_Run` shape and would be added when the backend is built.

### Live updates (SSE invalidation scopes)

Two new invalidation scopes on the global events coordinator: `harnesses`,
`delegated_runs`. The detail page registers refetch on each. Backend will emit
these off the existing `HARNESS_STATUS` / `DELEGATED_RUN_*` runtime events.

## Frontend types (`apps/web/src/lib/api/types.ts`)

```ts
interface HarnessStatus { name: string; installed: boolean; authenticated: boolean }
interface HarnessStatusList { items: HarnessStatus[] }

type DelegatedRunStatus = 'running' | 'completed' | 'failed' | 'stopped'
interface DelegatedRun {
  run_id: string
  harness: string
  model: string
  status: DelegatedRunStatus
  result: string | null
  error: Record<string, unknown> | null
  started_at: string
}
interface DelegatedRunList { items: DelegatedRun[] }
```

Endpoint functions added to `endpoints.ts`:
`fetchHarnesses`, `installHarness`, `authenticateHarness`, `fetchDelegatedRuns`,
`stopDelegatedRun`.

## Mock layer (`apps/web/src/mock/`)

- `state/harnesses.ts` — mutable per-devcontainer harness map seeded from
  `state/seeds.ts`; install/authenticate mutate it so refetch reflects the change.
- `state/delegatedRuns.ts` — mutable per-devcontainer run list; `stop` flips a
  run to `stopped`.
- `fixtures.ts` — baseline harness statuses (Claude Code ready; Codex installed,
  unauth; Cursor not installed) and a couple of delegated runs (one running, one
  completed, one failed) for the healthy scenario.
- `handlers.ts` — MSW handlers for the five new endpoints, reading/mutating the
  stores above.
- `RailMock.tsx` — add scope-emit buttons for `harnesses` and `delegated_runs`
  so live-update behavior is inspectable.
- Scenario coverage: surface harness/delegated-run states across existing
  scenarios where meaningful (e.g. agent-disconnected hides/disables actions).

## Cleanup (frontend only)

`DevcontainerDetail.tsx` is the only non-test, non-mock consumer of the chat
stack. Rebuild it from scratch and delete the now-dead code:

- `apps/web/src/lib/stream/` (per-session live turn-delta stream).
- `apps/web/src/lib/chat/` (chat interaction helpers).
- Agent-session endpoint functions + DTO types in `lib/api/` (`fetchAgentSessions`,
  `fetchAgentSession`, `start/stop/resume/deleteAgentSession`,
  `fetchAgentSessionTranscript`, `openAgentSessionStream`; `AgentSession*`,
  `Transcript*`, `*Delta` types).
- Mock: `mock/state/agentSessions.ts`, `mock/agentSessionStreams.ts`, agent-session
  handlers in `handlers.ts`, agent-session fixtures/seeds, and their tests.

Backend agent-session routes/schemas/repositories are **left untouched**.

## Affected files

- Re-theme: `apps/web/src/index.css`, sweep `routes/`, `components/`.
- Rebuild: `apps/web/src/routes/DevcontainerDetail.tsx` (+ small presentational
  components, possibly extracted into `components/`).
- API: `lib/api/types.ts`, `lib/api/endpoints.ts`.
- Mock: `mock/handlers.ts`, `mock/fixtures.ts`, `mock/state/*`, `mock/RailMock.tsx`,
  `mock/state/seeds.ts`.
- Delete: `lib/stream/`, `lib/chat/`, agent-session mock/state/streams + tests.
- Docs: update `apps/web/CLAUDE.md` (remove stream/chat lib references, add
  harness/delegated-run endpoints + mock stores).

## Testing

- Mock handler tests for the five new endpoints (status read, install/authenticate
  flag flips, stop transition).
- Component tests for the harness list (icon/disabled states per harness state)
  and delegated-runs feed (empty state, stop action, expand result/error).
- Remove obsolete chat/stream/agent-session tests.
- `pnpm test`, `pnpm build` green.

## Open questions

None.
