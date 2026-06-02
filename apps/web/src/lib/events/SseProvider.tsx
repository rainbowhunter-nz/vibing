import { useEffect, useRef, useState } from 'react'
import { createCoordinator } from './coordinator'
import type { Coordinator } from './coordinator'
import type { Health, InvalidationCallback, Scope } from './types'
import { SseContext } from './SseContext'

export function SseProvider({ children }: { children: React.ReactNode }) {
  const coordRef = useRef<Coordinator | null>(null)
  const [health, setHealth] = useState<Health>('disconnected')

  useEffect(() => {
    // onHealthChange fires from open/error callbacks — not directly in effect body
    const coord = createCoordinator(setHealth)
    coordRef.current = coord
    coord.connect()

    return () => {
      coord.disconnect()
      coordRef.current = null
    }
  }, [])

  function register(scope: Scope, cb: InvalidationCallback) {
    if (!coordRef.current) return () => {}
    return coordRef.current.register(scope, cb)
  }

  return <SseContext.Provider value={{ register, health }}>{children}</SseContext.Provider>
}
