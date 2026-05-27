import { useEffect, useState, type ReactNode } from 'react'
import { PageHeader } from '../components/PageHeader'
import { fetchSettings, type SettingsResponse } from '../lib/api'
import { cn } from '../lib/cn'

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; settings: SettingsResponse }
  | { kind: 'error' }

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

function Toggle({
  id,
  checked,
  onChange,
}: {
  id: string
  checked: boolean
  onChange: (next: boolean) => void
}) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 cursor-pointer items-center rounded-full transition-colors',
        checked ? 'bg-accent' : 'bg-surface-muted',
      )}
    >
      <span
        className={cn(
          'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
          checked ? 'translate-x-[18px]' : 'translate-x-0.5',
        )}
      />
    </button>
  )
}

function runtimeLabel(value: boolean | null): string {
  if (value === null) return 'Not detected yet'
  return value ? 'Available' : 'Not found'
}

export function Settings() {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [notifications, setNotifications] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('system')
  const [sidebarWidth, setSidebarWidth] = useState(240)

  useEffect(() => {
    let cancelled = false
    fetchSettings()
      .then((settings) => {
        if (!cancelled) setState({ kind: 'ready', settings })
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

  return (
    <>
      <PageHeader title="Settings" />
      <div className="flex-1 overflow-auto">
        <Section title="Preferences">
          <p className="text-xs text-text-muted">
            Placeholder controls — not wired up yet.
          </p>
          <Field label="Enable notifications">
            <div className="flex items-center gap-2">
              <Toggle
                id="notifications-toggle"
                checked={notifications}
                onChange={setNotifications}
              />
              <span className="text-[13px] text-text-muted">{notifications ? 'On' : 'Off'}</span>
            </div>
          </Field>
          <Field label="Display name" id="display-name">
            <input
              id="display-name"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="e.g. Hank"
              className={cn(inputClass, 'max-w-[320px]')}
            />
          </Field>
          <Field label="Theme" id="theme-select">
            <select
              id="theme-select"
              value={theme}
              onChange={(e) => setTheme(e.target.value as typeof theme)}
              className={cn(inputClass, 'max-w-[240px]')}
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </Field>
          <Field label="Sidebar width" id="sidebar-width">
            <div className="flex max-w-[320px] items-center gap-3">
              <input
                id="sidebar-width"
                type="range"
                min={200}
                max={320}
                step={4}
                value={sidebarWidth}
                onChange={(e) => setSidebarWidth(Number(e.target.value))}
                className="flex-1 accent-accent"
              />
              <span className="w-12 text-right text-[13px] tabular-nums text-text-muted">
                {sidebarWidth}px
              </span>
            </div>
          </Field>
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
