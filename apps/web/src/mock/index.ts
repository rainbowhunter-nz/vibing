export { SCENARIOS, getScenario, setScenario, subscribe, resetScenario, DEFAULT_SCENARIO } from './scenario'
export type { Scenario } from './scenario'
export { useScenario } from './useScenario'

export function isMockMode(): boolean {
  return import.meta.env.VITE_API_MOCKING === 'true'
}
