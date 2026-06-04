export { SCENARIOS, getScenario, setScenario, subscribe, resetScenario, DEFAULT_SCENARIO } from './scenario'
export type { Scenario } from './scenario'
export { useScenario } from './useScenario'
export { installMockEventSource, emitInvalidation, setStreamState, getStreamState, subscribeStreamState, resetMockEvents } from './events'
export type { StreamState } from './events'
export { useStreamState } from './useMockSse'

export function isMockMode(): boolean {
  return import.meta.env.VITE_API_MOCKING === 'true'
}
