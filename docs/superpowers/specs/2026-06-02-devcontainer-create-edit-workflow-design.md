# Devcontainer create & edit workflow — design

**Ticket:** VIB-61
**Date:** 2026-06-02
**Status:** Approved

## Problem

The web UI lists Devcontainers and supports start / stop / delete, but has no way to
**create** or **edit** one. The empty state ("Devcontainers will appear here once you
add a local folder") points nowhere. The backend already exposes the needed endpoints
(`POST /devcontainers`, `PATCH /devcontainers/{id}`), so this is a frontend-only gap.

## Backend constraints (ground truth)

From `src/vibing_api/api/schemas/devcontainers.py`:

- **Create** `DevcontainerCreateRequest`: `name` (min_length=1), `local_path` (min_length=1).
- **Update** `DevcontainerUpdateRequest`: `name` (optional, min_length=1), `status`.
  `local_path` is **not** updatable.
- No path-existence validation at the API; `local_path` validity only surfaces later
  when the host worker starts the container.

Implications: **edit is a rename** (path immutable); the browser cannot validate a host
path, so path is free text.

## Decisions

| Question | Decision |
|----------|----------|
| Presentation | **Modal dialog** (one reusable component, `create` + `edit` modes) |
| Edit scope | **Rename only** — `local_path` shown read-only |
| Edit entry point | **Pencil icon** in the list row actions |
| Create entry points | Header **"+ Add"** button + **empty-state CTA** |

## Workflow

### Component

`DevcontainerFormModal` in `apps/web/src/components/`. Props: `mode: 'create' | 'edit'`,
`devcontainer?` (prefill for edit), `onClose`, `onSuccess`. Centered dialog over a dimmed
backdrop. Dismissed by Cancel, backdrop click, or Esc. Owned by `Devcontainers.tsx`, which
holds the open / mode / target state (mirroring how it holds `pending` today).

### Entry points

- **Header "+ Add"** on the Devcontainers list → create mode.
- **Empty state** becomes actionable: folder icon, title "No devcontainers yet", primary
  **"Add devcontainer"** button → create mode. (Update existing `EmptyState` usage to take
  an action, or render a button alongside it.)
- **Pencil icon** in each row's action group (before start/stop/delete) → edit mode,
  prefilled.

### Fields

| Field | Create | Edit | Rules |
|-------|--------|------|-------|
| Name | editable | editable | required, non-empty |
| Local path | editable, helper "Absolute path on the host machine." | **read-only**, helper "Path can't be changed. Delete and re-add to move it." | required, non-empty |

### Validation

- Client-side mirrors backend `min_length=1`.
- Primary button disabled until all required (non-read-only) fields are non-empty.
- Inline messages on submit/blur: `"Name is required."`, `"Local path is required."`.
- No path-format validation — real path errors surface on container start.

### States

- **Submitting:** inputs + buttons disabled; spinner + "Creating…" / "Saving…" in the
  primary button (reuse the existing row-action spinner style).
- **Server error:** show the backend error-envelope message (`ApiError.message` from
  `lib/api/client`) as a red banner at the top of the modal body; form stays filled for
  retry.

### Success → return to list

Modal closes; the list refetches via the existing `refetch()` from `useApiQuery` (same path
as start/stop/delete). The new / renamed row appears (a new container briefly shows
`created` status). SSE invalidation already keeps the list live — no extra wiring. No
confirmation screen or toast.

## API / types

No changes. `createDevcontainer` and `updateDevcontainer` already exist in
`apps/web/src/lib/api/endpoints.ts`; `DevcontainerCreateBody` / `DevcontainerUpdateBody`
already exist in `types.ts`.

## Out of scope (future)

- **Editing `local_path`** — needs a backend change to accept `local_path` in
  `DevcontainerUpdateRequest`. Deferred to a separate ticket.
- Host filesystem path picker / browse — not feasible from the browser.

## Testing

- `DevcontainerFormModal`: create submits `{name, local_path}`; edit submits `{name}` and
  renders path read-only; required-field validation disables submit and shows messages;
  submitting disables the form; server error renders the banner and preserves input.
- `Devcontainers`: "+ Add" and empty-state CTA open create mode; pencil opens edit mode
  prefilled; success closes the modal and refetches the list.
