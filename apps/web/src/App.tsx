import { useEffect, useState } from 'react'
import './App.css'

type HealthState =
  | { kind: 'loading' }
  | { kind: 'ok'; service: string }
  | { kind: 'error'; message: string }

function App() {
  const [health, setHealth] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/v1/health', { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const body = (await res.json()) as { status: string; service: string }
        if (body.status !== 'ok') {
          throw new Error(`status=${body.status}`)
        }
        setHealth({ kind: 'ok', service: body.service })
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        const message = err instanceof Error ? err.message : String(err)
        setHealth({ kind: 'error', message })
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="vibing-shell">
      <h1>Vibing</h1>
      <p className="tagline">Local operations center for AI coding agents.</p>
      <section className="status-card" data-state={health.kind}>
        <h2>Backend</h2>
        {health.kind === 'loading' && <p>Checking <code>/api/v1/health</code>…</p>}
        {health.kind === 'ok' && (
          <p>
            Connected to <code>{health.service}</code>.
          </p>
        )}
        {health.kind === 'error' && (
          <p>
            Could not reach backend: <code>{health.message}</code>
          </p>
        )}
      </section>
    </main>
  )
}

export default App
