export const SCENARIOS = ['happy', 'empty', 'api-error', 'network-down', 'stale-action', 'not-found'] as const
export type Scenario = (typeof SCENARIOS)[number]

const STORAGE_KEY = 'vib_mock_scenario'
const DEFAULT: Scenario = 'happy'

function readStorage(): Scenario {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v && (SCENARIOS as readonly string[]).includes(v)) return v as Scenario
  } catch {
    // storage unavailable
  }
  return DEFAULT
}

function writeStorage(s: Scenario) {
  try {
    localStorage.setItem(STORAGE_KEY, s)
  } catch {
    // storage unavailable
  }
}

let current: Scenario = readStorage()
const listeners = new Set<() => void>()

export function getScenario(): Scenario {
  return current
}

export function setScenario(s: Scenario) {
  current = s
  writeStorage(s)
  listeners.forEach((fn) => fn())
}

/** Subscribe to scenario changes; returns unsubscribe. */
export function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** Reset to default without touching storage (for tests). */
export function resetScenario() {
  current = DEFAULT
  listeners.forEach((fn) => fn())
}

export { DEFAULT as DEFAULT_SCENARIO }
