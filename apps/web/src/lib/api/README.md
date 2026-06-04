# Frontend API client

All backend calls live under `/api/v1` (see `src/vibing_api/main.py`). In dev, Vite proxies that prefix to `http://localhost:8000` (`apps/web/vite.config.ts`); in production the same path is served from the FastAPI process. **Never hardcode `http://localhost:8000`** — always call through this module.

## Calling endpoints

```ts
import { fetchDevcontainers } from '../lib/api'

const { items } = await fetchDevcontainers()
```

Each `fetchX` returns the parsed JSON response, typed against the backend Pydantic model. Failures throw:

- `ApiError` — backend returned non-2xx with the standard envelope `{error: {code, message, details}}`. Inspect `err.code` (e.g. `DEVCONTAINER_NOT_FOUND`, `VALIDATION_ERROR`).
- `ApiError` with `code: 'HTTP_ERROR'` — non-2xx without the envelope (e.g. 500 with an HTML body).
- `NetworkError` — `fetch` itself rejected (backend down, DNS failure, etc.).

## Pattern A — `useApiQuery` (use this for new screens)

```tsx
import { useApiQuery, fetchDevcontainers } from '../lib/api'

function DevcontainersPage() {
  const { state, refetch } = useApiQuery(fetchDevcontainers, [])

  if (state.kind === 'loading') return <Spinner />
  if (state.kind === 'error') return <ErrorView onRetry={refetch} />
  return <List items={state.data.items} />
}
```

The hook owns loading state, cancellation on unmount, and refetch. Pass `[]` for an on-mount fetch, or `[id]` to refetch when an id changes.

## Pattern B — manual `useEffect` (legacy)

`Devcontainers.tsx`, `Settings.tsx`, and `RailBackend.tsx` were written before the hook existed; they roll their own `{loading | ready | error}` state machine + `cancelled` flag. Don't copy that pattern into new code — use `useApiQuery`.

## Error handling

```ts
import { ApiError, deleteDevcontainer } from '../lib/api'

try {
  await deleteDevcontainer(id)
} catch (err) {
  if (err instanceof ApiError && err.code === 'DEVCONTAINER_NOT_FOUND') {
    showToast('Devcontainer already deleted')
  } else {
    showToast('Something went wrong')
  }
}
```

## Adding an endpoint

1. Add the response shape to `types.ts`.
2. Add `fetchX = (): Promise<XResponse> => getJson('/x')` (or `sendJson` for writes) to `endpoints.ts`.
3. The barrel (`index.ts`) re-exports it automatically.

## Mocking in tests

Two patterns:

**Unit tests (single component):** stub individual endpoint functions: `vi.mock('../../lib/api/endpoints')` then `vi.mocked(fetchX).mockResolvedValue(...)`. See `src/routes/__tests__/Settings.test.tsx`.

**Integration / mock-mode tests:** use `setupServer` from `msw/node` with the shared handlers in `src/mock/handlers.ts`. The server intercepts fetch at the network level so the real client code runs unmodified. See `src/mock/__tests__/bootstrap.test.tsx`.
