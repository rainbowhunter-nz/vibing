# Live Runtime Log Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-shot runtime-log fetch with a true tail-follow live stream over chunked HTTP, torn down via `AbortController` ↔ client disconnect.

**Architecture:** `GET /{id}/runtime-logs/stream` returns a `StreamingResponse(text/plain)` driven by an injectable `log_streamer` seam whose default spawns `docker exec <cid> tail -n +1 -f /tmp/vibing-runtime.log` and yields its stdout chunks (killing the subprocess in `finally`). The browser reads `response.body.getReader()` and appends chunks to the Logs dialog; closing the dialog aborts the fetch, which the server sees as a disconnect and uses to kill the `tail`. `tail -n +1 -f` delivers the full existing log first, then follows — so it fully replaces the removed one-shot path. See spec `docs/superpowers/specs/2026-06-23-runtime-log-live-streaming-design.md` and ADR-0018.

**Tech Stack:** Python 3.13, FastAPI/Starlette `StreamingResponse`, asyncio subprocess, pytest (backend); React + TypeScript, `fetch`/`ReadableStream`, vitest, MSW, Playwright (frontend).

## Global Constraints

- Python checks must pass: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`. Run from repo root `/workspaces/vibing` (uses `uv`).
- Frontend checks must pass: `pnpm test`, `pnpm build` (tsc), `pnpm e2e` — run from `apps/web` (the project uses **pnpm**, never npm).
- In-container log path constant is `CONTAINER_LOG_PATH = "/tmp/vibing-runtime.log"` (already defined in `runtime_injector.py`). Stream command: `tail -n +1 -f` (whole file from the top, then follow).
- Keep SSE invalidation-only (ADR-0005): log **data** must NOT go over the `/events` SSE stream — it rides this dedicated chunked-HTTP endpoint.
- All frontend backend access goes through `src/lib/api/`; components never `fetch` directly. New API call ⇒ update `endpoints.ts` + `types.ts` + Control Plane API Mocking in the same change.
- DTO types in `apps/web/src/lib/api/types.ts` stay in sync with backend Pydantic schemas.
- The one-shot log path is **removed end-to-end** (subsumed by streaming): injector `read_log`, `RuntimeService.read_log`, `RuntimeLogs` schema, `GET /{id}/runtime-logs`, the `RuntimeLogs` TS type, `fetchRuntimeLogs`, and their tests.
- Prefer self-explanatory code; comment only the non-obvious. Minimum code that solves the problem.

---

## File Structure

**Task 1 — Backend (atomic `read_log`→`stream_log` swap; independently green)**
- Modify `src/vibing_api/core/runtime_injector.py` — `log_streamer` seam + default `tail -f` impl; `stream_log`; remove `read_log`.
- Modify `src/vibing_api/core/runtime_service.py` — `stream_log` delegating; remove `read_log`.
- Modify `src/vibing_api/api/routes/devcontainers.py` — `GET /{id}/runtime-logs/stream` (`StreamingResponse`); remove the one-shot route.
- Modify `src/vibing_api/api/schemas/devcontainers.py` — remove `RuntimeLogs`.
- Modify `tests/api/test_runtime_injector.py`, `tests/api/test_runtime_service.py`, `tests/api/test_runtime_lifecycle_api.py` — migrate read_log → stream_log tests.

**Task 2 — Frontend (atomic; endpoints + component + mock + unit tests; green)**
- Modify `apps/web/src/lib/api/types.ts` — remove `RuntimeLogs`.
- Modify `apps/web/src/lib/api/endpoints.ts` — replace `fetchRuntimeLogs` with `streamRuntimeLogs`.
- Modify `apps/web/src/routes/DevcontainerDetail.tsx` — streaming Logs dialog (`useEffect`/`AbortController`, live indicator, auto-scroll).
- Modify `apps/web/src/mock/handlers.ts` — replace the `runtime-logs` handler with a `runtime-logs/stream` `ReadableStream` handler.
- Create `apps/web/src/lib/api/__tests__/streamRuntimeLogs.test.ts` — api-layer streaming test.
- Modify `apps/web/src/routes/DevcontainerDetail.test.tsx` — dialog-opens test.

**Task 3 — e2e + docs + ADR**
- Modify `apps/web/e2e/devcontainer-detail.spec.ts` — assert streamed content + live indicator.
- Modify `CONTEXT.md`, `src/vibing_api/CLAUDE.md`, `apps/web/CLAUDE.md`.
- Create `docs/adr/0018-runtime-logs-stream-live-via-tail-follow-over-chunked-http.md`; update `docs/adr/CLAUDE.md`.

---

## Task 1: Backend — stream_log replaces read_log

**Files:**
- Modify: `src/vibing_api/core/runtime_injector.py`
- Modify: `src/vibing_api/core/runtime_service.py`
- Modify: `src/vibing_api/api/routes/devcontainers.py:177-183`
- Modify: `src/vibing_api/api/schemas/devcontainers.py:40-41`
- Test: `tests/api/test_runtime_injector.py:87-107`, `tests/api/test_runtime_service.py:22-23,78-80`, `tests/api/test_runtime_lifecycle_api.py:53-62`

**Interfaces:**
- Produces: `RuntimeInjector(..., log_streamer: Callable[[str, str], AsyncIterator[bytes]] | None = None)`; `RuntimeInjector.stream_log(local_path: str) -> AsyncIterator[bytes]` (empty when no container).
- Produces: module-level `_default_log_streamer(engine: str, container_id: str) -> AsyncIterator[bytes]`.
- Produces: `RuntimeService.stream_log(local_path: str) -> AsyncIterator[bytes]`.
- Produces: `GET /devcontainers/{id}/runtime-logs/stream` → `StreamingResponse(media_type="text/plain")`; 404 `DEVCONTAINER_NOT_FOUND` for unknown id.
- Removes: injector `read_log`, `RuntimeService.read_log`, `RuntimeLogs` schema, `GET /{id}/runtime-logs`.

- [ ] **Step 1: Write the failing injector tests (replace the two `read_log` tests)**

In `tests/api/test_runtime_injector.py`, delete `test_read_log_returns_container_file_contents` and `test_read_log_returns_none_when_no_container` (lines 87-107) and add:

```python
def test_stream_log_yields_streamer_chunks(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        return RunResult(0, "", "")

    async def fake_streamer(engine, container_id):
        assert container_id == "deadbeef"
        yield b"install ok\n"
        yield b"runtime started\n"

    injector = RuntimeInjector(runner=runner, log_streamer=fake_streamer)

    async def collect():
        return [chunk async for chunk in injector.stream_log("/work/repo")]

    assert asyncio.run(collect()) == [b"install ok\n", b"runtime started\n"]


def test_stream_log_empty_when_no_container(tmp_path: Path) -> None:
    async def runner(command):
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "\n", "")  # no container id

    async def fake_streamer(engine, container_id):
        yield b"should not be reached"

    injector = RuntimeInjector(runner=runner, log_streamer=fake_streamer)

    async def collect():
        return [chunk async for chunk in injector.stream_log("/work/repo")]

    assert asyncio.run(collect()) == []
```

- [ ] **Step 2: Write the failing service test (replace `read_log`)**

In `tests/api/test_runtime_service.py`, replace `FakeInjector.read_log` (lines 22-23) with a `stream_log` method:

```python
    def stream_log(self, local_path: str):
        async def gen():
            yield b"chunk1 "
            yield b"chunk2"

        return gen()
```

Replace `test_read_log_delegates_to_injector` (lines 78-80) with:

```python
def test_stream_log_delegates_to_injector() -> None:
    svc = _service(FakeInjector())

    async def collect():
        return [chunk async for chunk in svc.stream_log("/work/repo")]

    assert asyncio.run(collect()) == [b"chunk1 ", b"chunk2"]
```

(`FakeInjector.__init__` still sets `self.log` — leave it; it is now unused but harmless. Optionally remove the `self.log = "log contents"` line.)

- [ ] **Step 3: Write the failing API test (replace the one-shot endpoint test)**

In `tests/api/test_runtime_lifecycle_api.py`, replace `test_runtime_logs_endpoint_returns_content` (lines 53-62) with:

```python
def test_runtime_logs_stream_endpoint_streams_content(client: TestClient) -> None:
    dc_id = _create(client)

    def fake_stream(local_path: str):
        async def gen():
            yield b"hello "
            yield b"from the runtime"

        return gen()

    client.app.state.runtime_service.stream_log = fake_stream  # type: ignore[union-attr]
    resp = client.get(f"/api/v1/devcontainers/{dc_id}/runtime-logs/stream")
    assert resp.status_code == 200
    assert resp.text == "hello from the runtime"


def test_runtime_logs_stream_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/devcontainers/nope/runtime-logs/stream")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/api/test_runtime_injector.py tests/api/test_runtime_service.py tests/api/test_runtime_lifecycle_api.py -q`
Expected: FAIL — `AttributeError`/`TypeError` (`log_streamer` kwarg unknown, `stream_log` missing) and 404 on the new route (not registered).

- [ ] **Step 5: Implement the injector seam + `stream_log`, remove `read_log`**

In `src/vibing_api/core/runtime_injector.py`:

Replace the imports block (lines 13-18) with:

```python
import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from logzero import logger

from vibing_api.core.runtime_injector_url import resolve_runtime_control_plane_url
from vibing_api.core.devcontainer_cli import Runner, _default_runner
```

After the path constants (after line 26), add the default streamer:

```python
async def _default_log_streamer(engine: str, container_id: str) -> AsyncIterator[bytes]:
    proc = await asyncio.create_subprocess_exec(
        engine,
        "exec",
        container_id,
        "tail",
        "-n",
        "+1",
        "-f",
        CONTAINER_LOG_PATH,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert proc.stdout is not None
    try:
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            yield chunk
    finally:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
```

In `__init__`, add the parameter (after `runner: Runner | None = None,` on line 38) and assignment:

```python
        runner: Runner | None = None,
        log_streamer: Callable[[str, str], AsyncIterator[bytes]] | None = None,
    ) -> None:
        self._cli = devcontainer_cli
        self._runtime_url = runtime_control_plane_url
        self._engine = engine
        self._uv_binary = uv_binary
        self._wheel_dir = wheel_dir
        self._runner = runner or _default_runner
        self._log_streamer = log_streamer or _default_log_streamer
```

Replace the `read_log` method (lines 129-141) with:

```python
    async def stream_log(self, local_path: str) -> AsyncIterator[bytes]:
        container_id = await self.resolve_container_id(local_path)
        if container_id is None:
            return
        async for chunk in self._log_streamer(self._engine, container_id):
            yield chunk
```

Update the module docstring (lines 6-7): change "`stop_runtime` and `read_log` drive the container via `<engine> exec`." to "`stop_runtime` kills via the PID file and `stream_log` tail-follows the unified log, both via `<engine> exec`."

- [ ] **Step 6: Implement `RuntimeService.stream_log`, remove `read_log`**

In `src/vibing_api/core/runtime_service.py`:

Add to imports (after line 8 `import asyncio`):

```python
from collections.abc import AsyncIterator
```

Replace the `read_log` method (lines 64-65) with:

```python
    def stream_log(self, local_path: str) -> AsyncIterator[bytes]:
        return self._injector.stream_log(local_path)
```

Update the module docstring (line 3): "runtime stop, and on-demand log retrieval" → "runtime stop, and live log streaming".

- [ ] **Step 7: Replace the route + remove the `RuntimeLogs` schema**

In `src/vibing_api/api/schemas/devcontainers.py`, delete the `RuntimeLogs` class (lines 40-41) and the blank line around it.

In `src/vibing_api/api/routes/devcontainers.py`:
- In the schema import group (lines 3-11), remove `RuntimeLogs`.
- Add to the FastAPI import (line 1): `from fastapi import APIRouter, Request, Response, status` stays; add a new import line below it: `from fastapi.responses import StreamingResponse`.
- Replace the `runtime_logs` route (lines 177-183) with:

```python
@router.get("/{devcontainer_id}/runtime-logs/stream")
async def runtime_logs_stream(devcontainer_id: str, request: Request) -> StreamingResponse:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    stream = request.app.state.runtime_service.stream_log(resolved.local_path)
    return StreamingResponse(stream, media_type="text/plain")
```

- [ ] **Step 8: Run the targeted tests to verify they pass**

Run: `uv run pytest tests/api/test_runtime_injector.py tests/api/test_runtime_service.py tests/api/test_runtime_lifecycle_api.py -q`
Expected: PASS.

- [ ] **Step 9: Run the full suite + checks**

Run: `uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`
Expected: all green. (If any other test referenced `read_log`/`RuntimeLogs`, none should — grep `grep -rn "read_log\|RuntimeLogs" src tests` must return nothing.)

- [ ] **Step 10: Commit**

```bash
git add src/vibing_api/core/runtime_injector.py src/vibing_api/core/runtime_service.py src/vibing_api/api/routes/devcontainers.py src/vibing_api/api/schemas/devcontainers.py tests/api/test_runtime_injector.py tests/api/test_runtime_service.py tests/api/test_runtime_lifecycle_api.py
git commit -m "feat(api): stream runtime logs via tail -f over chunked HTTP, replacing one-shot read_log"
```

---

## Task 2: Frontend — streaming Logs dialog

**Files:**
- Modify: `apps/web/src/lib/api/types.ts:87-89`
- Modify: `apps/web/src/lib/api/endpoints.ts:1,15,52-53`
- Modify: `apps/web/src/routes/DevcontainerDetail.tsx` (imports + `RuntimeSection`)
- Modify: `apps/web/src/mock/handlers.ts:173-183`
- Create: `apps/web/src/lib/api/__tests__/streamRuntimeLogs.test.ts`
- Modify: `apps/web/src/routes/DevcontainerDetail.test.tsx`

**Interfaces:**
- Consumes: `GET /{id}/runtime-logs/stream` (Task 1).
- Produces: `streamRuntimeLogs(id: string, signal: AbortSignal, onChunk: (text: string) => void): Promise<void>`.
- Removes: `RuntimeLogs` type, `fetchRuntimeLogs`.

- [ ] **Step 1: Write the failing api-layer streaming test**

Create `apps/web/src/lib/api/__tests__/streamRuntimeLogs.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { streamRuntimeLogs } from '../endpoints'

describe('streamRuntimeLogs', () => {
  it('accumulates chunked content from the stream endpoint', async () => {
    const parts: string[] = []
    await streamRuntimeLogs('dc-seed-0001', new AbortController().signal, (t) => parts.push(t))
    expect(parts.join('')).toContain('runtime started')
  })
})
```

(This relies on the global MSW server the existing vitest setup starts — the same one the mock-state and route tests use. If the test file needs an explicit server import, mirror whatever an existing test under `apps/web/src` does to get MSW active.)

- [ ] **Step 2: Run it to verify it fails**

Run (from `apps/web`): `pnpm test src/lib/api/__tests__/streamRuntimeLogs.test.ts`
Expected: FAIL — `streamRuntimeLogs` is not exported (and the `/runtime-logs/stream` mock handler does not exist yet).

- [ ] **Step 3: Replace `fetchRuntimeLogs` with `streamRuntimeLogs`; remove the `RuntimeLogs` type**

In `apps/web/src/lib/api/types.ts`, delete the `RuntimeLogs` interface (lines 87-89).

In `apps/web/src/lib/api/endpoints.ts`:
- Line 1: change `import { getJson, sendJson } from './client'` to `import { ApiError, getJson, sendJson } from './client'`.
- Remove `RuntimeLogs,` from the type import block (line 15).
- Replace `fetchRuntimeLogs` (lines 52-53) with:

```typescript
export async function streamRuntimeLogs(
  id: string,
  signal: AbortSignal,
  onChunk: (text: string) => void,
): Promise<void> {
  const res = await fetch(`/api/v1/devcontainers/${encodeURIComponent(id)}/runtime-logs/stream`, { signal })
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, 'HTTP_ERROR', `runtime log stream failed (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}
```

- [ ] **Step 4: Add the streaming mock handler**

In `apps/web/src/mock/handlers.ts`, replace the `runtime-logs` GET handler (lines 173-183) with:

```typescript
  http.get('*/api/v1/devcontainers/:id/runtime-logs/stream', ({ params }) => {
    const failure = scenarioFailure('DEVCONTAINER_NOT_FOUND')
    if (failure) return failure
    try {
      dc.getDevcontainer(params.id as string)
    } catch (e) {
      if (e instanceof dc.NotFoundError) return notFound(params.id as string)
      throw e
    }
    const chunks = ['mock runtime log\n', 'install ok\n', 'runtime started\n']
    const stream = new ReadableStream({
      start(controller) {
        const enc = new TextEncoder()
        for (const c of chunks) controller.enqueue(enc.encode(c))
        controller.close()
      },
    })
    return new HttpResponse(stream, { headers: { 'Content-Type': 'text/plain' } })
  }),
```

- [ ] **Step 5: Run the api-layer test to verify it passes**

Run (from `apps/web`): `pnpm test src/lib/api/__tests__/streamRuntimeLogs.test.ts`
Expected: PASS.

- [ ] **Step 6: Write the failing dialog test**

In `apps/web/src/routes/DevcontainerDetail.test.tsx`, add a test using the file's existing render helper (e.g. `renderDetail(base)` where `base.runtime.state === 'connected'` — match the helper name actually present in the file):

```typescript
  it('opens the runtime logs dialog with a live indicator', async () => {
    renderDetail(base)
    fireEvent.click(screen.getByTitle('View runtime logs'))
    expect(await screen.findByText('Runtime logs')).toBeTruthy()
    expect(screen.getByText('live')).toBeTruthy()
  })
```

(Use the file's existing imports for `fireEvent`/`screen`; if it only imports `screen`, add `fireEvent` from `@testing-library/react`.)

- [ ] **Step 7: Run it to verify it fails**

Run (from `apps/web`): `pnpm test src/routes/DevcontainerDetail.test.tsx`
Expected: FAIL — `streamRuntimeLogs` not yet wired into the component; `fetchRuntimeLogs` import is now broken (removed in Step 3), so this also surfaces as a compile/import error until Step 8.

- [ ] **Step 8: Rewrite the Logs dialog in `RuntimeSection` to stream**

In `apps/web/src/routes/DevcontainerDetail.tsx`:
- Line 1 import: ensure `useEffect`, `useState`, and `useRef` are imported: `import { useEffect, useRef, useState } from 'react'`.
- In the api import block (lines 9-21), replace `fetchRuntimeLogs,` with `streamRuntimeLogs,`.
- Replace the `RuntimeSection` body from the `const [logs, ...]`/`viewLogs`/dialog region (current lines 190-238) with:

```tsx
  const [logs, setLogs] = useState('')
  const [showLogs, setShowLogs] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const preRef = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (!showLogs) return
    const controller = new AbortController()
    setLogs('')
    setStreaming(true)
    streamRuntimeLogs(dc.id, controller.signal, (text) => setLogs((prev) => prev + text))
      .catch((e) => {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setLogs((prev) => prev + `\n[stream error: ${e instanceof Error ? e.message : String(e)}]`)
      })
      .finally(() => setStreaming(false))
    return () => controller.abort()
  }, [showLogs, dc.id])

  useEffect(() => {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight
  }, [logs])

  return (
    <section className="mb-5">
      <SectionTitle>Runtime</SectionTitle>
      <div className="flex items-center gap-2 text-[13px]">
        <span
          className={cn(
            'h-2 w-2 rounded-full',
            connected ? 'bg-ok' : launching ? 'bg-accent' : 'bg-text-subtle',
          )}
        />
        <span className={connected ? 'text-text' : 'text-text-muted'}>{RUNTIME_LABEL[state]}</span>
        <div className="ml-auto flex items-center gap-1">
          <IconButton title="View runtime logs" busy={false} onClick={() => setShowLogs(true)}>
            <span className="text-[11px] font-medium">Logs</span>
          </IconButton>
          {connected ? (
            <IconButton title="Stop runtime" busy={busy} onClick={() => onAction('stop-runtime')}>
              <StopIcon />
            </IconButton>
          ) : (
            <IconButton
              title={running ? 'Inject runtime' : 'Start the container to inject runtime'}
              busy={busy && running}
              disabled={!running}
              onClick={() => onAction('inject')}
            >
              <InjectIcon />
            </IconButton>
          )}
        </div>
      </div>
      {showLogs && (
        <Dialog title="Runtime logs" onClose={() => setShowLogs(false)}>
          <div className="mb-1 flex items-center gap-1.5 text-[11px] text-text-muted">
            <span className={cn('h-1.5 w-1.5 rounded-full', streaming ? 'bg-ok' : 'bg-text-subtle')} />
            {streaming ? 'live' : 'ended'}
          </div>
          <pre
            ref={preRef}
            className="max-h-80 overflow-auto whitespace-pre-wrap text-[12px] text-text-muted"
          >
            {logs || 'Waiting for output…'}
          </pre>
        </Dialog>
      )}
    </section>
  )
```

(The `running`/`state`/`connected`/`launching` consts above this region are unchanged.)

- [ ] **Step 9: Run the full frontend unit suite + build**

Run (from `apps/web`): `pnpm test && pnpm build`
Expected: PASS (vitest green; tsc clean). Verify no stale refs: `grep -rn "fetchRuntimeLogs\|RuntimeLogs" apps/web/src` returns nothing.

- [ ] **Step 10: Commit**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/lib/api/endpoints.ts apps/web/src/routes/DevcontainerDetail.tsx apps/web/src/mock/handlers.ts apps/web/src/lib/api/__tests__/streamRuntimeLogs.test.ts apps/web/src/routes/DevcontainerDetail.test.tsx
git commit -m "feat(web): live-streaming runtime logs dialog (chunked fetch + AbortController)"
```

---

## Task 3: e2e + docs + ADR-0018

**Files:**
- Modify: `apps/web/e2e/devcontainer-detail.spec.ts:35-41`
- Modify: `CONTEXT.md`, `src/vibing_api/CLAUDE.md`, `apps/web/CLAUDE.md`
- Create: `docs/adr/0018-runtime-logs-stream-live-via-tail-follow-over-chunked-http.md`
- Modify: `docs/adr/CLAUDE.md`

- [ ] **Step 1: Strengthen the e2e logs test**

In `apps/web/e2e/devcontainer-detail.spec.ts`, replace the `runtime section: connected shows Stop and logs dialog` test (lines 35-41) with:

```typescript
test('runtime section: connected shows Stop and live logs dialog', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0001')
  await expect(page.getByRole('main').getByText('Connected', { exact: true })).toBeVisible()
  await expect(page.getByTitle('Stop runtime')).toBeVisible()
  await page.getByTitle('View runtime logs').click()
  await expect(page.getByRole('dialog').getByText('Runtime logs')).toBeVisible()
  await expect(page.getByRole('dialog').getByText(/runtime started/)).toBeVisible()
})
```

- [ ] **Step 2: Run e2e**

Run (from `apps/web`): `pnpm e2e`
Expected: PASS (all specs). Chromium is installed under `~/.cache`.

- [ ] **Step 3: Update `CONTEXT.md`**

In the Runtime-lifecycle section, replace the diagnosability sentence's "post-launch failures live in the in-container runtime log, fetched on demand (`runtime-logs`)" with: "post-launch output lives in the in-container runtime log, **streamed live** (`tail -f`) over a chunked-HTTP `runtime-logs/stream` endpoint while the Logs view is open."

- [ ] **Step 4: Update `src/vibing_api/CLAUDE.md`**

- In the `runtime_injector.py` bullet: change `read_log` (`<engine> exec cat`, on demand)` to `stream_log` (`<engine> exec tail -n +1 -f` via an injectable `log_streamer` seam; kills the proc on disconnect)`.
- In the `runtime_service.py` bullet: change "on-demand `read_log`" to "live `stream_log`".
- In the `devcontainers.py` route bullet: change "`GET /{id}/runtime-logs` returns `{content}` (on-demand `docker exec cat`)" to "`GET /{id}/runtime-logs/stream` returns a `text/plain` chunked `StreamingResponse` (`tail -f`)".

- [ ] **Step 5: Update `apps/web/CLAUDE.md`**

- In the detail-view runtime paragraph: change the Logs description to "a "Logs" button that opens a dialog **streaming** the runtime log live (chunked-fetch + `AbortController`; a live/ended indicator)".
- In the `src/mock/` line: change the runtime endpoints note from `runtime-logs` (GET) to `runtime-logs/stream` (GET, chunked `ReadableStream`).

- [ ] **Step 6: Create ADR-0018**

Create `docs/adr/0018-runtime-logs-stream-live-via-tail-follow-over-chunked-http.md`:

```markdown
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
```

- [ ] **Step 7: Update the ADR index**

In `docs/adr/CLAUDE.md`, add after the 0017 entry:

```markdown
- [0018](0018-runtime-logs-stream-live-via-tail-follow-over-chunked-http.md) — Runtime logs stream live via `docker exec tail -f` over a chunked-HTTP `runtime-logs/stream` endpoint (not SSE — preserves 0005; not WS); viewer-scoped held `tail` torn down on disconnect; replaces 0017's on-demand fetch.
```

- [ ] **Step 8: Verify docs coherence + commit**

Run: `grep -rn "read_log\|runtime-logs'\|on demand" CONTEXT.md src/vibing_api/CLAUDE.md apps/web/CLAUDE.md` — confirm no stale on-demand/`read_log` runtime-log references remain (ignore unrelated hits).

```bash
git add apps/web/e2e/devcontainer-detail.spec.ts CONTEXT.md src/vibing_api/CLAUDE.md apps/web/CLAUDE.md docs/adr/0018-runtime-logs-stream-live-via-tail-follow-over-chunked-http.md docs/adr/CLAUDE.md
git commit -m "test(web): e2e for live log stream; docs + ADR-0018 for runtime log streaming"
```

---

## Self-Review

**Spec coverage:**
- True tail-follow streaming via `tail -n +1 -f` → Task 1 (injector default streamer). ✓
- Chunked HTTP `StreamingResponse` text/plain → Task 1 (route). ✓
- `AbortController` ↔ disconnect teardown killing the `tail` → Task 1 (`_default_log_streamer` finally) + Task 2 (`controller.abort()` cleanup). ✓
- Injectable `log_streamer` seam for testability → Task 1. ✓
- One-shot path removed end-to-end (injector/service `read_log`, schema, route, TS type, `fetchRuntimeLogs`, tests) → Tasks 1 & 2. ✓
- Browser reader + dialog wiring + live indicator + auto-scroll → Task 2. ✓
- Mock streaming handler → Task 2. ✓
- Tests: backend stream_log + endpoint; frontend api-layer stream + dialog; e2e content + live → Tasks 1, 2, 3. ✓
- Error handling: no-container → empty stream; unknown id → 404; abort ignored; idle-linger accepted → Task 1 (route/stream_log) + Task 2 (catch). ✓
- Docs (CONTEXT, both CLAUDE.md) + ADR-0018 + index → Task 3. ✓
- ADR-0005 SSE-invalidation-only respected (no data on SSE) → Global Constraints + ADR-0018. ✓

**Placeholder scan:** No TBD/"handle edge cases"/"similar to Task N"; every code step shows full code. The only adaptation notes (match the existing test render-helper name; ensure MSW server import mirrors an existing test) are concrete instructions, not placeholders.

**Type consistency:** `stream_log(local_path) -> AsyncIterator[bytes]` identical across injector (Task 1) and service (Task 1), consumed by the route (Task 1) and the api test. `log_streamer: Callable[[str, str], AsyncIterator[bytes]]` matches `_default_log_streamer(engine, container_id)`. `streamRuntimeLogs(id, signal, onChunk)` defined in endpoints (Task 2 Step 3) and consumed by the component (Task 2 Step 8) and the api-layer test (Task 2 Step 1) with identical signature. `RuntimeLogs`/`fetchRuntimeLogs`/`read_log` removed in every layer they appear.

**Scope:** Single coherent feature; three tasks, each ends green (Task 1 backend atomic; Task 2 frontend atomic; Task 3 docs/e2e). Land in order.
```
