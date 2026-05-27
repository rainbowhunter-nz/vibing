import { useEffect, useState, type ReactNode } from 'react'
import { PageHeader } from '../components/PageHeader'
import { fetchSettings, updateSettings, type SettingsResponse } from '../lib/api'
import { cn } from '../lib/cn'

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; settings: SettingsResponse }
  | { kind: 'error' }

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const RUNTIME_ROWS: [keyof SettingsResponse['runtime'], string][] = [
  ['docker', 'Docker'],
  ['podman', 'Podman'],
  ['devcontainer_cli', 'Dev Container CLI'],
  ['claude_code', 'Claude Code'],
]

const inputClass =
  'rounded-md border border-border bg-bg px-3 py-1.5 text-[13px] text-text outline-none focus:border-accent'
const readOnlyClass =
  'rounded-md border border-border bg-surface-muted px-3 py-1.5 text-[13px] text-text-muted'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-border px-6 py-5">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

function Field({
  label,
  id,
  hint,
  children,
}: {
  label: string
  id?: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1">
      {id ? (
        <label htmlFor={id} className="text-[13px] font-medium text-text">
          {label}
        </label>
      ) : (
        <span className="text-[13px] font-medium text-text">{label}</span>
      )}
      {children}
      {hint && <p className="text-xs text-text-muted">{hint}</p>}
    </div>
  )
}

function runtimeLabel(value: boolean | null): string {
  if (value === null) return 'Not detected yet'
  return value ? 'Available' : 'Not found'
}

export function Settings() {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [storageLocation, setStorageLocation] = useState('')
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (cancelled) return
        setState({ kind: 'ready', settings })
        setStorageLocation(settings.workspace_storage_location)
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (state.kind === 'loading') {
    return (
      <>
        <PageHeader title="Settings" />
        <div className="flex h-full items-center justify-center p-8 text-[13px] text-text-muted">
          Loading settings…
        </div>
      </>
    )
  }

  if (state.kind === 'error') {
    return (
      <>
        <PageHeader title="Settings" />
        <div className="flex h-full items-center justify-center p-8">
          <div className="max-w-[320px] text-center">
            <h2 className="mb-1.5 text-[15px] font-semibold text-text">Couldn't load settings</h2>
            <p className="text-[13px] text-text-muted">
              Check that the backend is running, then reload the page.
            </p>
          </div>
        </div>
      </>
    )
  }

  const { settings } = state
  const trimmed = storageLocation.trim()
  const dirty = trimmed !== settings.workspace_storage_location
  const canSave = dirty && trimmed.length > 0 && saveStatus !== 'saving'

  function handleSave() {
    const value = storageLocation.trim()
    if (!value) return
    setSaveStatus('saving')
    updateSettings({ workspace_storage_location: value })
      .then((updated) => {
        setState({ kind: 'ready', settings: updated })
        setSaveStatus('saved')
      })
      .catch(() => setSaveStatus('error'))
  }

  return (
    <>
      <PageHeader title="Settings" />
      <div className="flex-1 overflow-auto">
        <Section title="Workspace">
          <Field
            label="Storage location"
            id="storage-location"
            hint="Where Vibing stores workspace data on this machine."
          >
            <input
              id="storage-location"
              type="text"
              value={storageLocation}
              onChange={(e) => {
                setStorageLocation(e.target.value)
                setSaveStatus('idle')
              }}
              className={cn(inputClass, 'max-w-[480px]')}
            />
          </Field>
          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={!canSave}
              className={cn(
                'rounded-md px-3 py-1.5 text-[13px] font-medium',
                canSave
                  ? 'cursor-pointer bg-accent text-white hover:opacity-90'
                  : 'cursor-not-allowed bg-surface-muted text-text-muted',
              )}
            >
              {saveStatus === 'saving' ? 'Saving…' : 'Save'}
            </button>
            {saveStatus === 'saved' && <span className="text-xs text-ok">Saved</span>}
            {saveStatus === 'error' && <span className="text-xs text-bad">Couldn't save</span>}
          </div>
        </Section>

        <Section title="Backend">
          <Field label="Host" id="backend-host" hint="Set via environment; applies on restart.">
            <input
              id="backend-host"
              type="text"
              value={settings.backend_host}
              readOnly
              className={cn(readOnlyClass, 'max-w-[480px]')}
            />
          </Field>
          <Field label="Port" id="backend-port">
            <input
              id="backend-port"
              type="text"
              value={String(settings.backend_port)}
              readOnly
              className={cn(readOnlyClass, 'max-w-[160px]')}
            />
          </Field>
        </Section>

        <Section title="Editor">
          <Field label="Preferred editor" id="editor-preference" hint="Coming soon.">
            <input
              id="editor-preference"
              type="text"
              value=""
              placeholder="Coming soon"
              disabled
              className={cn(readOnlyClass, 'max-w-[480px]')}
            />
          </Field>
        </Section>

        <Section title="Notifications">
          <Field label="Notifications" hint="Coming soon.">
            <label className="inline-flex cursor-not-allowed items-center gap-2">
              <input type="checkbox" disabled className="h-4 w-4 cursor-not-allowed" />
              <span className="text-[13px] text-text-muted">Coming soon</span>
            </label>
          </Field>
        </Section>

        <Section title="Runtime detection">
          <div className="space-y-2">
            {RUNTIME_ROWS.map(([key, label]) => (
              <div key={key} className="flex max-w-[480px] items-center justify-between">
                <span className="text-[13px] text-text">{label}</span>
                <span className="text-xs text-text-muted">{runtimeLabel(settings.runtime[key])}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </>
  )
}
