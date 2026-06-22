# Live runtime log streaming

## Goal

Make the Devcontainer Runtime log view **stream live** (true tail-follow) instead of the
current one-shot fetch. When a user opens the Logs dialog, they see the full existing log
immediately and then watch new output arrive in real time — primarily to watch a runtime come
up or fail right after Inject.

## Background

Today (ADR-0017): the Logs dialog calls `fetchRuntimeLogs` once → `GET /{id}/runtime-logs` →
`RuntimeService.read_log` → injector `read_log` → `docker exec <cid> cat /tmp/vibing-runtime.log`.
It returns a frozen snapshot. The unified log holds `uv tool install` output, runtime startup,
and runtime stdout — small and bursty, not a high-volume firehose.

## Approach

Chunked HTTP streaming (`StreamingResponse`, `text/plain`) driven by `docker exec tail -f`, torn
down via `AbortController` ↔ client-disconnect. SSE was rejected to keep ADR-0005's boundary (the
app SSE stream stays invalidation-only, never data); WebSocket was rejected as unneeded
bidirectional transport.

### Data flow

```
Browser (Logs dialog)                 Control Plane                          Container
 fetch(.../runtime-logs/stream) ────▶  StreamingResponse(text/plain)
 reader.read() loop  ◀────chunks─────  async-gen yields proc.stdout  ◀──── docker exec tail -n +1 -f /tmp/vibing-runtime.log
 close dialog → abort()  ───────────▶  client disconnect → gen finally: proc.kill()
```

`tail -n +1 -f` emits the **entire existing file first**, then follows — so it fully subsumes the
one-shot fetch. The one-shot path is **removed** (see Scope).

## Components

### Backend

**`src/vibing_api/core/runtime_injector.py`** — replace `read_log` with:

- `stream_log(local_path: str) -> AsyncIterator[bytes]`: resolve the container id via the existing
  `_runner` (`docker ps -q --filter label=...`); if none, return immediately (empty stream).
  Otherwise delegate to an injectable `log_streamer` seam and re-yield its chunks.
- A new constructor param `log_streamer: Callable[[str, str], AsyncIterator[bytes]] | None = None`
  (args: `engine`, `container_id`). Default implementation: a module-level async generator that
  spawns `asyncio.create_subprocess_exec(engine, "exec", container_id, "tail", "-n", "+1", "-f",
  CONTAINER_LOG_PATH, stdout=PIPE, stderr=DEVNULL)`, loops `await proc.stdout.read(4096)` yielding
  non-empty chunks, and in `finally` `proc.kill()` + `await proc.wait()` (suppressing
  `ProcessLookupError`). The seam mirrors the existing `Runner` injection so the streaming behavior
  is unit-testable with a fake generator; the default docker-exec wrapper is the only un-unit-tested
  piece (like `_default_runner`).

Remove the old `read_log` method.

**`src/vibing_api/core/runtime_service.py`** — replace `read_log` with
`stream_log(local_path) -> AsyncIterator[bytes]` that returns/delegates to `injector.stream_log`.
No transient/state involvement (logs are independent of the launching/connected lifecycle).

**`src/vibing_api/api/routes/devcontainers.py`** — replace the `GET /{id}/runtime-logs` route with:

```python
@router.get("/{devcontainer_id}/runtime-logs/stream")
async def runtime_logs_stream(devcontainer_id: str, request: Request) -> StreamingResponse:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    stream = request.app.state.runtime_service.stream_log(resolved.local_path)
    return StreamingResponse(stream, media_type="text/plain")
```

Starlette cancels the async generator on client disconnect, so the generator's `finally` kills the
`tail` subprocess — the teardown path. Remove the `RuntimeLogs` schema.

### Frontend

**`apps/web/src/lib/api/endpoints.ts`** — replace `fetchRuntimeLogs` with:

```typescript
export async function streamRuntimeLogs(
  id: string,
  signal: AbortSignal,
  onChunk: (text: string) => void,
): Promise<void> {
  const res = await fetch(`/api/v1/devcontainers/${encodeURIComponent(id)}/runtime-logs/stream`, { signal })
  if (!res.ok || !res.body) throw new ApiError(...)   // match the project's ApiError shape
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}
```

Keeps `fetch` in the api layer per the `apps/web` convention. Remove the `RuntimeLogs` type and
`fetchRuntimeLogs`.

**`apps/web/src/routes/DevcontainerDetail.tsx` — `RuntimeSection`** — the Logs dialog drives the
stream from a `useEffect` keyed on the open state: on open, create an `AbortController`, call
`streamRuntimeLogs` appending each chunk to the `logs` string, auto-scroll to bottom, and show a
small "● live" indicator; the effect cleanup calls `abort()` (on close/unmount), which ends the
reader loop and triggers server teardown. An aborted fetch (`AbortError`) is ignored; other errors
render a short message in the dialog.

### Mock

**`apps/web/src/mock/handlers.ts`** — replace the `runtime-logs` handler with a
`GET …/runtime-logs/stream` handler returning a `ReadableStream` body (`text/plain`) that enqueues
the canned log content in two or three chunks then closes — deterministic for tests, and
demonstrates the append/auto-scroll path in dev. Honor the request's abort signal (cancel the
stream).

## Error handling

- **No container / stopped devcontainer:** `resolve_container_id` → None → empty stream (200, closes
  immediately). UI shows the empty/"no runtime log" state.
- **Unknown devcontainer id:** 404 `DEVCONTAINER_NOT_FOUND` (before streaming begins).
- **Client closes dialog:** `AbortController.abort()` → reader loop ends → server generator
  cancelled → `tail` killed.
- **Idle-tail linger (accepted):** killing the local `docker exec` does not reliably kill an *idle*
  in-container `tail` (no write → no SIGPIPE). A lingering idle `tail` in an ephemeral, single-user
  container is cheap and dies on the next log line or when the container stops. Documented, not
  mitigated.

## Testing

- **Backend** (`tests/api/`): `stream_log` re-yields a fake `log_streamer`'s chunks; container-None
  yields nothing; the endpoint streams the body (TestClient reads streamed content) with a fake
  streamer injected into `app.state`; unknown id → 404. Replaces the removed `read_log` tests.
- **Frontend** (`apps/web`): mock handler test for the stream endpoint (chunked content); a
  component/integration test opens the Logs dialog and asserts the accumulated streamed content
  renders.
- **e2e** (`apps/web/e2e/devcontainer-detail.spec.ts`): open Logs on the connected seed
  (`dc-seed-0001`), assert streamed content appears and the "live" indicator is visible.

## Docs

- `CONTEXT.md`: runtime-logs description — "fetched on demand" → "streamed live (`tail -f`) while the
  Logs view is open."
- `src/vibing_api/CLAUDE.md`, `apps/web/CLAUDE.md`: update the runtime-logs endpoint/dialog
  description.
- **New ADR-0018** (live log streaming): records chunked-HTTP-over-`tail -f` chosen *instead of* SSE
  (preserving ADR-0005's invalidation-only SSE boundary) and instead of WebSocket; the
  viewer-scoped held `tail` (distinct from ADR-0017's rejected hold of the runtime *launch*
  process, since it doesn't affect runtime liveness); the idle-linger caveat; and amends ADR-0017's
  "logs fetched on demand" stance. Add the index entry in `docs/adr/CLAUDE.md`.

## Scope

In: the streaming endpoint + injector/service `stream_log`, the frontend streaming reader + dialog
wiring, mock, tests, docs, ADR-0018. **Removed** (subsumed by streaming): `GET /{id}/runtime-logs`,
`RuntimeService.read_log`, injector `read_log`, `RuntimeLogs` schema/type, `fetchRuntimeLogs`, and
their tests.

Out: reconnect/backoff on the browser side (reopening the dialog restarts the stream); log
download/persistence; log filtering or search; streaming any log other than
`/tmp/vibing-runtime.log`.
