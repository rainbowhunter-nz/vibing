export interface HealthResponse {
  status: string
  service: string
}

export interface ConfigResponse {
  app_name: string
  api_v1_prefix: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    throw new Error(`${path} ${res.status}`)
  }
  return (await res.json()) as T
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/v1/health')
}

export function fetchConfig(): Promise<ConfigResponse> {
  return getJson<ConfigResponse>('/api/v1/config')
}
