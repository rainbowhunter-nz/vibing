import { useContext } from 'react'
import { SseContext } from './SseContext'
import type { SseContextValue } from './SseContext'

export function useSseInvalidation(): SseContextValue {
  const ctx = useContext(SseContext)
  if (!ctx) throw new Error('useSseInvalidation must be used inside <SseProvider>')
  return ctx
}
