import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { createDevcontainer, updateDevcontainer, type Devcontainer } from '../lib/api'
import { cn } from '../lib/cn'

type DevcontainerFormModalProps =
  | { mode: 'create'; devcontainer?: never; onClose: () => void; onSuccess: () => void }
  | { mode: 'edit'; devcontainer: Devcontainer; onClose: () => void; onSuccess: () => void }

const inputClass =
  'w-full rounded-md border border-border bg-bg px-2.5 py-2 text-[13px] text-text outline-none focus:border-accent disabled:cursor-not-allowed'

const spinner = (
  <span className="mr-1.5 inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/50 border-t-white" />
)

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="mb-3.5">
      <label htmlFor={id} className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.04em] text-text-muted">
        {label}
      </label>
      {children}
    </div>
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
        if (!devcontainer) return
        await updateDevcontainer(devcontainer.id, { name: name.trim() })
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
          <Field id="dc-name" label="Name">
            <input
              id="dc-name"
              autoFocus
              value={name}
              disabled={submitting}
              onChange={(e) => setName(e.target.value)}
              className={cn(inputClass, showErrors && nameError && 'border-bad')}
            />
            {showErrors && nameError && <p className="mt-1 text-[11px] text-bad">{nameError}</p>}
          </Field>
          <Field id="dc-local-path" label="Local path">
            <input
              id="dc-local-path"
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
