# Runtime logs stream live via `tail -f` over chunked HTTP, not SSE

ADR-0017 fetched the runtime log on demand (`GET /runtime-logs` → `docker exec cat`), a frozen
snapshot. To let a user watch a runtime come up or fail in real time, the Logs view now **streams
live**: `GET /{id}/runtime-logs/stream` returns a `text/plain` `StreamingResponse` fed by
`docker exec <cid> tail -n +1 -f /tmp/vibing-runtime.log` — the whole existing log first, then
follow. The browser reads `response.body.getReader()` and appends chunks; closing the dialog
`AbortController.abort()`s the fetch, which the server sees as a client disconnect and uses to kill
the `tail`. This **replaces** the one-shot endpoint (the stream subsumes it).

**Chunked HTTP, not SSE.** SSE was rejected to preserve ADR-0005's boundary — the app SSE stream
carries lightweight invalidations only, never data. A dedicated chunked-HTTP endpoint keeps log
*content* off the invalidation stream, fits the existing `fetch` api layer, and gives precise
teardown via `AbortController` ↔ server disconnect. WebSocket was rejected as unneeded bidirectional
transport with no browser-side infrastructure today.

**The held `tail` is viewer-scoped**, not lifecycle-coupled. ADR-0017 rejected holding the runtime's
*launch* process because it would bind runtime liveness to the Control Plane. A `tail -f` held only
while a Logs dialog is open is different: it observes, it does not own the runtime, and it tears down
when the viewer closes. The streaming generator's `finally` kills the subprocess on disconnect.

**Accepted caveat:** killing the local `docker exec` does not reliably kill an *idle* in-container
`tail` (no write → no SIGPIPE). A lingering idle `tail` in an ephemeral, single-user container is
cheap and dies on the next log line or when the container stops. Not mitigated.

Amends ADR-0017 (logs were "fetched on demand"; now streamed live). Respects ADR-0005
(SSE stays invalidation-only).

Status: accepted
