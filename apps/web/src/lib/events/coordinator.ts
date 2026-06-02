import type { Health, InvalidationCallback, InvalidationEvent, Scope } from './types'

const SSE_URL = '/api/v1/events'

export interface Coordinator {
  connect(): void
  disconnect(): void
  register(scope: Scope, cb: InvalidationCallback): () => void
  readonly health: Health
}

export function createCoordinator(onHealthChange?: (h: Health) => void): Coordinator {
  const registry = new Map<Scope, Set<InvalidationCallback>>()
  let es: EventSource | null = null
  let _health: Health = 'disconnected'

  function setHealth(h: Health) {
    _health = h
    onHealthChange?.(h)
  }

  function handleInvalidate(e: Event) {
    const msg = e as MessageEvent
    try {
      const ev: InvalidationEvent = JSON.parse(msg.data as string)
      registry.get(ev.scope)?.forEach((cb) => cb(ev))
    } catch {
      // malformed event — ignore
    }
  }

  return {
    connect() {
      if (es !== null) return // idempotent
      es = new EventSource(SSE_URL)
      setHealth('reconnecting')

      es.onopen = () => setHealth('connected')

      es.onerror = () => {
        // readyState CONNECTING (0) = auto-reconnect; CLOSED (2) = fatal
        setHealth(es!.readyState === 2 ? 'disconnected' : 'reconnecting')
        // Native EventSource handles reconnect — never open a second connection
      }

      es.addEventListener('invalidate', handleInvalidate)
    },

    disconnect() {
      es?.close()
      es = null
      setHealth('disconnected')
    },

    register(scope, cb) {
      if (!registry.has(scope)) registry.set(scope, new Set())
      registry.get(scope)!.add(cb)
      return () => registry.get(scope)?.delete(cb)
    },

    get health() {
      return _health
    },
  }
}
