# Devcontainer create/edit modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable modal to the web UI for creating and renaming Devcontainers, reachable from a header button, an empty-state CTA, and a per-row pencil icon.

**Architecture:** One `DevcontainerFormModal` component with `create` and `edit` modes, owned by the `Devcontainers` route (which holds open/mode/target state alongside its existing `pending` state). Create posts `{name, local_path}`; edit patches `{name}` with `local_path` read-only. Success closes the modal and refetches the list. Shared `StateMessage`/`EmptyState`/`PageHeader` gain an optional `action` slot.

**Tech Stack:** React + TypeScript, Tailwind (theme tokens in `apps/web/src/index.css`), Vitest + Testing Library. Backend endpoints and API client functions already exist (`createDevcontainer`, `updateDevcontainer` in `apps/web/src/lib/api/endpoints.ts`).

**Spec:** `docs/superpowers/specs/2026-06-02-devcontainer-create-edit-workflow-design.md`

**Ticket:** VIB-66

---

## File Structure

- **Create** `apps/web/src/components/DevcontainerFormModal.tsx` — the modal (form, validation, submit/error states, both modes).
- **Create** `apps/web/src/components/__tests__/DevcontainerFormModal.test.tsx` — unit tests for the modal.
- **Modify** `apps/web/src/components/StateMessage.tsx` — add optional `action?: ReactNode` rendered under the helper.
- **Modify** `apps/web/src/components/EmptyState.tsx` — forward an optional `action` prop.
- **Modify** `apps/web/src/components/PageHeader.tsx` — add optional `action?: ReactNode` rendered right-aligned.
- **Modify** `apps/web/src/routes/Devcontainers.tsx` — header "+ Add", empty-state CTA, per-row pencil, modal state + success refetch.
- **Modify** `apps/web/src/routes/__tests__/Devcontainers.test.tsx` — integration tests for the entry points.

Run all web commands from `apps/web/`. Full check: `pnpm test --run && pnpm build`.

---

### Task 1: Optional action slot on shared state/header components

**Files:**
- Modify: `apps/web/src/components/StateMessage.tsx`
- Modify: `apps/web/src/components/EmptyState.tsx`
- Modify: `apps/web/src/components/PageHeader.tsx`
- Test: `apps/web/src/components/__tests__/StateMessage.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `apps/web/src/components/__tests__/StateMessage.test.tsx`:

```tsx
it('renders an action when provided', () => {
  render(
    <StateMessage
      icon={<span>i</span>}
      title="No devcontainers yet"
      helper="helper"
      action={<button>Add devcontainer</button>}
    />,
  )
  expect(screen.getByRole('button', { name: 'Add devcontainer' })).toBeTruthy()
})
```

If the file lacks imports, ensure the top has:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StateMessage } from '../StateMessage'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test --run src/components/__tests__/StateMessage.test.tsx`
Expected: FAIL — `action` is not a valid prop / button not found.

- [ ] **Step 3: Add the `action` prop to StateMessage**

Replace the body of `apps/web/src/components/StateMessage.tsx` with:

```tsx
import type { ReactNode } from 'react'
import { cn } from '../lib/cn'

interface StateMessageProps {
  icon: ReactNode
  title: string
  helper: string
  tone?: 'muted' | 'error'
  action?: ReactNode
}

const TONE_CHIP: Record<'muted' | 'error', string> = {
  muted: 'bg-surface-muted text-accent',
  error: 'bg-red-100 text-bad',
}

export function StateMessage({ icon, title, helper, tone = 'muted', action }: StateMessageProps) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-[320px] text-center">
        <div
          aria-hidden="true"
          className={cn(
            'mx-auto mb-3.5 flex h-10 w-10 items-center justify-center rounded-[10px]',
            TONE_CHIP[tone],
          )}
        >
          {icon}
        </div>
        <h2 className="mb-1.5 text-[15px] font-semibold text-text">{title}</h2>
        <p className="text-[13px] text-text-muted">{helper}</p>
        {action && <div className="mt-4 flex justify-center">{action}</div>}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Forward `action` through EmptyState**

Replace `apps/web/src/components/EmptyState.tsx` with:

```tsx
import type { ReactNode } from 'react'
import { StateMessage } from './StateMessage'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  helper: string
  action?: ReactNode
}

export function EmptyState(props: EmptyStateProps) {
  return <StateMessage {...props} tone="muted" />
}
```

- [ ] **Step 5: Add `action` to PageHeader**

Replace `apps/web/src/components/PageHeader.tsx` with:

```tsx
import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  crumbs?: string
  action?: ReactNode
}

export function PageHeader({ title, crumbs, action }: PageHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-border px-6 py-3.5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text">{title}</h1>
        {crumbs && <div className="mt-0.5 text-[11px] text-text-muted">{crumbs}</div>}
      </div>
      {action}
    </header>
  )
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pnpm test --run src/components/__tests__/StateMessage.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/StateMessage.tsx apps/web/src/components/EmptyState.tsx apps/web/src/components/PageHeader.tsx apps/web/src/components/__tests__/StateMessage.test.tsx
git commit -m "VIB-66 add optional action slot to StateMessage/EmptyState/PageHeader"
```

---

### Task 2: DevcontainerFormModal — create mode

**Files:**
- Create: `apps/web/src/components/DevcontainerFormModal.tsx`
- Test: `apps/web/src/components/__tests__/DevcontainerFormModal.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `apps/web/src/components/__tests__/DevcontainerFormModal.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DevcontainerFormModal } from '../DevcontainerFormModal'
import { createDevcontainer, updateDevcontainer } from '../../lib/api'
import type { Devcontainer } from '../../lib/api/types'

vi.mock('../../lib/api/endpoints')
const mockCreate = vi.mocked(createDevcontainer)
const mockUpdate = vi.mocked(updateDevcontainer)

const existing: Devcontainer = {
  id: 'dc1',
  name: 'api-service',
  local_path: '/home/me/projects/api',
  status: 'stopped',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => cleanup())

describe('DevcontainerFormModal — create', () => {
  it('submits name and local_path', async () => {
    mockCreate.mockResolvedValue(existing)
    const onSuccess = vi.fn()
    render(<DevcontainerFormModal mode="create" onClose={vi.fn()} onSuccess={onSuccess} />)

    await userEvent.type(screen.getByLabelText('Name'), 'api-service')
    await userEvent.type(screen.getByLabelText('Local path'), '/home/me/projects/api')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(mockCreate).toHaveBeenCalledWith({ name: 'api-service', local_path: '/home/me/projects/api' })
    expect(onSuccess).toHaveBeenCalled()
  })

  it('disables submit until both fields are filled', async () => {
    render(<DevcontainerFormModal mode="create" onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Create' }).hasAttribute('disabled')).toBe(true)

    await userEvent.type(screen.getByLabelText('Name'), 'x')
    await userEvent.type(screen.getByLabelText('Local path'), '/p')
    expect(screen.getByRole('button', { name: 'Create' }).hasAttribute('disabled')).toBe(false)
  })

  it('shows the backend error message and keeps input on failure', async () => {
    mockCreate.mockRejectedValue(new Error('path does not exist'))
    render(<DevcontainerFormModal mode="create" onClose={vi.fn()} onSuccess={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('Name'), 'api-service')
    await userEvent.type(screen.getByLabelText('Local path'), '/bad')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    await screen.findByText('path does not exist')
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('api-service')
  })

  it('calls onClose on Cancel and on Escape', async () => {
    const onClose = vi.fn()
    render(<DevcontainerFormModal mode="create" onClose={onClose} onSuccess={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm test --run src/components/__tests__/DevcontainerFormModal.test.tsx`
Expected: FAIL — module `../DevcontainerFormModal` not found.

- [ ] **Step 3: Implement the modal (create mode)**

Create `apps/web/src/components/DevcontainerFormModal.tsx`:

```tsx
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { createDevcontainer, updateDevcontainer, type Devcontainer } from '../lib/api'
import { cn } from '../lib/cn'

type Mode = 'create' | 'edit'

interface DevcontainerFormModalProps {
  mode: Mode
  devcontainer?: Devcontainer
  onClose: () => void
  onSuccess: () => void
}

const inputClass =
  'w-full rounded-md border border-border bg-bg px-2.5 py-2 text-[13px] text-text outline-none focus:border-accent disabled:cursor-not-allowed'

const spinner = (
  <span className="mr-1.5 inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/50 border-t-white" />
)

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="mb-3.5 block">
      <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.04em] text-text-muted">
        {label}
      </span>
      {children}
    </label>
  )
}

export function DevcontainerFormModal({ mode, devcontainer, onClose, onSuccess }: DevcontainerFormModalProps) {
  const [name, setName] = useState(devcontainer?.name ?? '')
  const [localPath, setLocalPath] = useState(devcontainer?.local_path ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showErrors, setShowErrors] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const nameError = name.trim() === '' ? 'Name is required.' : null
  const pathError = localPath.trim() === '' ? 'Local path is required.' : null
  const isValid = mode === 'edit' ? !nameError : !nameError && !pathError

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setShowErrors(true)
    if (!isValid) return
    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'create') {
        await createDevcontainer({ name: name.trim(), local_path: localPath.trim() })
      } else {
        await updateDevcontainer(devcontainer!.id, { name: name.trim() })
      }
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  const title = mode === 'create' ? 'New devcontainer' : 'Edit devcontainer'
  const submitLabel = mode === 'create' ? 'Create' : 'Save'
  const submittingLabel = mode === 'create' ? 'Creating…' : 'Saving…'
  const readOnlyPath = mode === 'edit'

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-24"
      onClick={onClose}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-[340px] overflow-hidden rounded-[10px] border border-border bg-bg shadow-xl"
      >
        <div className="border-b border-border px-4 py-3.5 text-sm font-semibold text-text">{title}</div>
        <div className="p-4">
          {error && (
            <div className="mb-3.5 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-xs text-bad">
              {error}
            </div>
          )}
          <Field label="Name">
            <input
              aria-label="Name"
              autoFocus
              value={name}
              disabled={submitting}
              onChange={(e) => setName(e.target.value)}
              className={cn(inputClass, showErrors && nameError && 'border-bad')}
            />
            {showErrors && nameError && <p className="mt-1 text-[11px] text-bad">{nameError}</p>}
          </Field>
          <Field label="Local path">
            <input
              aria-label="Local path"
              value={localPath}
              disabled={submitting || readOnlyPath}
              readOnly={readOnlyPath}
              onChange={(e) => setLocalPath(e.target.value)}
              className={cn(
                inputClass,
                readOnlyPath && 'bg-surface-muted text-text-muted',
                showErrors && pathError && 'border-bad',
              )}
            />
            {readOnlyPath ? (
              <p className="mt-1 text-[11px] text-text-muted">
                Path can&apos;t be changed. Delete and re-add to move it.
              </p>
            ) : showErrors && pathError ? (
              <p className="mt-1 text-[11px] text-bad">{pathError}</p>
            ) : (
              <p className="mt-1 text-[11px] text-text-muted">Absolute path on the host machine.</p>
            )}
          </Field>
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <button
            type="button"
            disabled={submitting}
            onClick={onClose}
            className="rounded-md border border-border px-3.5 py-1.5 text-xs font-semibold text-text-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !isValid}
            className="flex items-center rounded-md bg-accent px-3.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            {submitting ? (
              <>
                {spinner}
                {submittingLabel}
              </>
            ) : (
              submitLabel
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm test --run src/components/__tests__/DevcontainerFormModal.test.tsx`
Expected: PASS (4 create-mode tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/DevcontainerFormModal.tsx apps/web/src/components/__tests__/DevcontainerFormModal.test.tsx
git commit -m "VIB-66 add DevcontainerFormModal create mode"
```

---

### Task 3: DevcontainerFormModal — edit mode

The implementation from Task 2 already handles edit mode (read-only path, `updateDevcontainer`). This task locks that behavior with tests.

**Files:**
- Test: `apps/web/src/components/__tests__/DevcontainerFormModal.test.tsx`

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/src/components/__tests__/DevcontainerFormModal.test.tsx`:

```tsx
describe('DevcontainerFormModal — edit', () => {
  it('prefills name and renders local path read-only', () => {
    render(<DevcontainerFormModal mode="edit" devcontainer={existing} onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('api-service')
    const path = screen.getByLabelText('Local path') as HTMLInputElement
    expect(path.value).toBe('/home/me/projects/api')
    expect(path.readOnly).toBe(true)
  })

  it('submits only the name via updateDevcontainer', async () => {
    mockUpdate.mockResolvedValue({ ...existing, name: 'renamed' })
    const onSuccess = vi.fn()
    render(<DevcontainerFormModal mode="edit" devcontainer={existing} onClose={vi.fn()} onSuccess={onSuccess} />)

    const nameInput = screen.getByLabelText('Name')
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'renamed')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(mockUpdate).toHaveBeenCalledWith('dc1', { name: 'renamed' })
    expect(onSuccess).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pnpm test --run src/components/__tests__/DevcontainerFormModal.test.tsx`
Expected: PASS (all create + edit tests). If `readOnly` or `Save` assertions fail, fix the Task 2 component rather than the test.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/__tests__/DevcontainerFormModal.test.tsx
git commit -m "VIB-66 cover DevcontainerFormModal edit mode"
```

---

### Task 4: Wire the modal into the Devcontainers route

**Files:**
- Modify: `apps/web/src/routes/Devcontainers.tsx`
- Test: `apps/web/src/routes/__tests__/Devcontainers.test.tsx`

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/src/routes/__tests__/Devcontainers.test.tsx`. Add `createDevcontainer` and `updateDevcontainer` to the existing import from `'../../lib/api'`, then add their mocks near the other `vi.mocked` lines:

```tsx
const mockCreate = vi.mocked(createDevcontainer)
const mockUpdate = vi.mocked(updateDevcontainer)
```

Then add this describe block:

```tsx
describe('Devcontainers create/edit entry points', () => {
  it('opens the create modal from the header Add button', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByRole('button', { name: '+ Add' }))
    expect(screen.getByRole('dialog', { name: 'New devcontainer' })).toBeTruthy()
  })

  it('opens the create modal from the empty-state CTA', async () => {
    mockFetch.mockResolvedValue({ items: [] })
    renderPage()
    await screen.findByText('No devcontainers yet')

    await userEvent.click(screen.getByRole('button', { name: 'Add devcontainer' }))
    expect(screen.getByRole('dialog', { name: 'New devcontainer' })).toBeTruthy()
  })

  it('opens the edit modal prefilled from the row pencil', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByTitle('Edit'))
    const dialog = screen.getByRole('dialog', { name: 'Edit devcontainer' })
    expect(dialog).toBeTruthy()
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('my-project')
  })

  it('closes the modal and refetches after a successful create', async () => {
    mockFetch.mockResolvedValue({ items: [sample] })
    mockCreate.mockResolvedValue(sample)
    renderPage()
    await screen.findByText('my-project')

    await userEvent.click(screen.getByRole('button', { name: '+ Add' }))
    await userEvent.type(screen.getByLabelText('Name'), 'new-one')
    await userEvent.type(screen.getByLabelText('Local path'), '/home/me/new-one')

    const callsBefore = mockFetch.mock.calls.length
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(mockFetch.mock.calls.length).toBeGreaterThan(callsBefore))
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm test --run src/routes/__tests__/Devcontainers.test.tsx`
Expected: FAIL — no `+ Add` button / no `Edit` title / no dialog.

- [ ] **Step 3: Add the pencil icon and `onEdit` to the table**

In `apps/web/src/routes/Devcontainers.tsx`, add an edit icon next to the other icon consts:

```tsx
const editIcon = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
)
```

Add `onEdit` to the `DevcontainerTable` props type and signature:

```tsx
function DevcontainerTable({
  items,
  pending,
  onStart,
  onStop,
  onDelete,
  onEdit,
}: {
  items: Devcontainer[]
  pending: PendingAction | null
  onStart: (id: string) => void
  onStop: (id: string) => void
  onDelete: (id: string) => void
  onEdit: (devcontainer: Devcontainer) => void
}) {
```

Inside the row action group, add the pencil button as the FIRST button (before Start):

```tsx
<button
  title="Edit"
  disabled={isBusy}
  onClick={() => onEdit(devcontainer)}
  className={cn(
    'flex h-7 w-7 items-center justify-center rounded-[5px]',
    isBusy
      ? 'cursor-not-allowed text-text-muted opacity-[0.4]'
      : 'cursor-pointer text-text-muted hover:bg-surface-muted',
  )}
>
  {editIcon}
</button>
```

- [ ] **Step 4: Wire modal state into the `Devcontainers` component**

Replace the `Devcontainers` function in `apps/web/src/routes/Devcontainers.tsx` with:

```tsx
export function Devcontainers() {
  const { state, refetch } = useApiQuery(fetchDevcontainers, [])
  const { register } = useSseInvalidation()
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [modal, setModal] = useState<{ mode: 'create' | 'edit'; dc?: Devcontainer } | null>(null)

  useEffect(() => register('devcontainers', refetch), [register, refetch])
  const crumbs = state.kind === 'ready' ? countLabel(state.data.items.length) : undefined

  async function handleAction(id: string, action: PendingAction['action'], fn: () => Promise<unknown>) {
    setPending({ id, action })
    setActionError(null)
    try {
      await fn()
      refetch()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(null)
    }
  }

  const addButton = (
    <button
      onClick={() => setModal({ mode: 'create' })}
      className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white"
    >
      + Add
    </button>
  )

  return (
    <>
      <PageHeader title="Devcontainers" crumbs={crumbs} action={addButton} />
      <div className="flex-1 overflow-auto">
        {actionError && (
          <div className="px-4 pt-3">
            <ErrorState title="Action failed" helper={actionError} />
          </div>
        )}
        <QueryBoundary state={state} error={<ErrorState {...loadError('devcontainers')} />}>
          {(data) =>
            data.items.length === 0 ? (
              <EmptyState
                icon={folderIcon}
                title="No devcontainers yet"
                helper="Add a local folder to get started."
                action={
                  <button
                    onClick={() => setModal({ mode: 'create' })}
                    className="rounded-md bg-accent px-3.5 py-2 text-xs font-semibold text-white"
                  >
                    Add devcontainer
                  </button>
                }
              />
            ) : (
              <DevcontainerTable
                items={data.items}
                pending={pending}
                onStart={(id) => handleAction(id, 'start', () => startDevcontainer(id))}
                onStop={(id) => handleAction(id, 'stop', () => stopDevcontainer(id))}
                onDelete={(id) => handleAction(id, 'delete', () => deleteDevcontainer(id))}
                onEdit={(dc) => setModal({ mode: 'edit', dc })}
              />
            )
          }
        </QueryBoundary>
      </div>
      {modal && (
        <DevcontainerFormModal
          mode={modal.mode}
          devcontainer={modal.dc}
          onClose={() => setModal(null)}
          onSuccess={() => {
            setModal(null)
            refetch()
          }}
        />
      )}
    </>
  )
}
```

- [ ] **Step 5: Add the modal import**

At the top of `apps/web/src/routes/Devcontainers.tsx`, add:

```tsx
import { DevcontainerFormModal } from '../components/DevcontainerFormModal'
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pnpm test --run src/routes/__tests__/Devcontainers.test.tsx`
Expected: PASS — all existing tests plus the 4 new entry-point tests.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/routes/Devcontainers.tsx apps/web/src/routes/__tests__/Devcontainers.test.tsx
git commit -m "VIB-66 wire create/edit modal into Devcontainers list"
```

---

### Task 5: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full web suite**

Run (from `apps/web/`): `pnpm test --run`
Expected: all suites PASS.

- [ ] **Step 2: Typecheck + build**

Run (from `apps/web/`): `pnpm build`
Expected: `tsc` reports no errors and Vite build succeeds.

- [ ] **Step 3: Lint**

Run (from `apps/web/`): `pnpm lint` (skip if no `lint` script exists)
Expected: no errors.

- [ ] **Step 4: Manual smoke (optional)**

Run `pnpm dev`, open the Devcontainers page: confirm "+ Add" opens the create modal, empty state shows "Add devcontainer", the row pencil opens a prefilled edit modal with a read-only path, and a successful submit closes the modal and refreshes the list.

- [ ] **Step 5: Final commit if anything changed**

```bash
git add -A
git commit -m "VIB-66 verify create/edit modal suite" || echo "nothing to commit"
```

---

## Self-Review Notes

- **Spec coverage:** modal presentation (Task 2), edit=rename + read-only path (Tasks 2–3), entry points header/empty-state/pencil (Task 4), fields + validation + submitting + error states (Task 2), success→close+refetch (Task 4). All covered.
- **Out of scope:** editing `local_path` is intentionally not implemented (read-only in edit mode) — separate ticket per spec.
- **Type consistency:** `DevcontainerFormModalProps` (`mode`, `devcontainer`, `onClose`, `onSuccess`) is used identically in the modal, its tests, and the route. `onEdit(devcontainer: Devcontainer)` matches the `setModal({ mode: 'edit', dc })` shape.
