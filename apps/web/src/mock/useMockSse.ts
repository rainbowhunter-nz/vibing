import { useSyncExternalStore } from 'react'
import { getStreamState, subscribeStreamState, type StreamState } from './events'

export function useStreamState(): StreamState {
  return useSyncExternalStore(subscribeStreamState, getStreamState)
}
