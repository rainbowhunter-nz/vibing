import { useSyncExternalStore } from 'react'
import { getScenario, setScenario, subscribe, type Scenario } from './scenario'

export function useScenario(): [Scenario, (s: Scenario) => void] {
  const scenario = useSyncExternalStore(subscribe, getScenario)
  return [scenario, setScenario]
}
