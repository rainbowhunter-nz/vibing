import { useCallback, useEffect, useRef, useState } from 'react'
import { createCoordinator } from './coordinator'
import type { Health, InvalidationCallback, Scope } from './types'
import { SseContext } from './SseContext'

export function SseProvider({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = useState<Health>('disconnected')

  // Create coordinator once synchronously so child effects can register before connect().
  const coordRef = useRef<ReturnType<typeof createCoordinator> | null>(null)
  if (coordRef.current === null) coordRef.current = createCoordinator(setHealth)

  useEffect(() => {
    coordRef.current!.connect()
    return () => coordRef.current!.disconnect()
  }, [])

  // Stable identity: body only reads coordRef (stable ref), so [] is correct.
  const register = useCallback((scope: Scope, cb: InvalidationCallback) => {
    return coordRef.current!.register(scope, cb)
  }, [])

  return <SseContext.Provider value={{ register, health }}>{children}</SseContext.Provider>
}
