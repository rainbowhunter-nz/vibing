# External-Subagent MCP Server Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `vibing-harness` MCP server a straightforward "external subagent" dispatcher — required run titles surfaced in the UI, a tighter tool surface, self-documenting server instructions, and a harness/model routing guide.

**Architecture:** Add a required `title` to `spawn`, flowed through `list_runs` → the runtime `delegated_runs` envelope → the Control-Plane API → the web rail. Collapse `get_status`/`get_result` MCP tools into one `get_run`, expose `list_runs` as a tool, and attach lean `instructions` to the FastMCP server pointing at a new guide doc.

**Tech Stack:** Python (`uv`, FastMCP, pydantic, pytest); React + Vite + TS + Tailwind (vitest, Playwright, MSW).

## Global Constraints

- TDD for every task: failing test first, minimal code, green, commit. Frequent commits.
- Python checks from repo root: `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`.
- Frontend checks from `apps/web`: `pnpm test`, `pnpm build`, `pnpm e2e`.
- `title` is **required** on `spawn` (no default) — a short human label.
- Rule of thumb (verbatim in instructions + guide): **cursor → `composer-2.5`** (or latest Composer); **codex → `gpt-5.5`** (or latest GPT).
- Empirical pins: codex on a ChatGPT-account login works with `gpt-5.5`; `-codex`-suffixed models are API-key-only and rejected on a ChatGPT plan. cursor model ids are validated against `cursor-agent models`.
- pydantic models ignore extra fields by default, so tasks are individually safe to land in order.
- Manager methods `get_status`/`get_result` stay (internal helpers / used by `await_run` and tests); only the **MCP tool** surface changes.

---

### Task 1: Run title on `spawn` (manager + MCP tool)

The manager and the MCP `spawn` tool share a type-coupled signature, so they change
together — otherwise `mypy src` breaks between tasks.

**Files:**
- Modify: `src/vibing_devcontainer_runtime/delegated_runs.py`
- Modify: `src/vibing_devcontainer_runtime/mcp_server.py` (the `spawn` tool only)
- Test: `tests/devcontainer_runtime/test_delegated_runs.py`, `tests/devcontainer_runtime/test_mcp_server.py`

**Interfaces:**
- Produces: `DelegatedRunManager.spawn(harness, model, prompt, title, *, cwd=None, detached=False)`; `_Run.title: str`; `list_runs()` items gain `"title": str`; MCP `spawn(harness, model, prompt, title, detached=False, cwd=None)` tool.

- [ ] **Step 1: Write the failing tests**

Add to `tests/devcontainer_runtime/test_delegated_runs.py`:

```python
def test_spawn_stores_title_in_list_runs():
    mgr = _mgr(factory=lambda *a: ScriptedProcess(CompletedCommand(0, "ok", "")))
    asyncio.run(mgr.spawn("codex", "gpt-5.5", "do it", "refactor auth retry"))
    item = mgr.list_runs()[0]
    assert item["title"] == "refactor auth retry"
    assert item["run_id"] == "run-1"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/devcontainer_runtime/test_delegated_runs.py::test_spawn_stores_title_in_list_runs -q`
Expected: FAIL — `spawn()` missing positional `title` / `TypeError`.

- [ ] **Step 3: Implement**

In `delegated_runs.py`, add the field to `_Run` (after `model`):

```python
    title: str = ""
```

Change `spawn` signature and the `_Run` construction:

```python
    async def spawn(
        self,
        harness: str,
        model: str,
        prompt: str,
        title: str,
        *,
        cwd: str | None = None,
        detached: bool = False,
    ) -> dict[str, Any]:
        descriptor = self._descriptors[harness]  # KeyError on unknown harness
        if not await descriptor.is_authenticated(self._executor):
            raise RuntimeError(f"harness {harness} is not authenticated")
        if self._active() >= self._max:
            raise RuntimeError("delegated runs at capacity")

        self._counter += 1
        run = _Run(
            run_id=f"run-{self._counter}",
            harness=harness,
            model=model,
            title=title,
            started_at=_now(),
        )
        self._runs[run.run_id] = run
```

Add `"title": r.title,` to each dict in `list_runs()` (place it right after `"run_id"`).

- [ ] **Step 4: Update existing `spawn` call sites in the same test file**

Every existing `mgr.spawn(...)` call in `tests/devcontainer_runtime/test_delegated_runs.py` now needs a `title` argument. Add a 4th positional `"t"` to each call. The calls to update (pass `"t"` as the title):

```python
mgr.spawn("codex", "gpt-5.4", "do it", "t")          # test_blocking_spawn_returns_result
mgr.spawn("codex", "m", "p", "t")                    # all other spawn calls
mgr.spawn("codex", "m", "p", "t", detached=True)     # the detached ones keep their kwarg
```

Apply to every `spawn(` call in the file (blocking and detached). The expected result dicts (e.g. `{"run_id": "run-1", "status": "completed", "result": "the answer"}`) are unchanged — `spawn`'s return shape does not include the title.

- [ ] **Step 5: Update the MCP `spawn` tool and its test double**

In `tests/devcontainer_runtime/test_mcp_server.py`, change `FakeDelegatedRuns.spawn` to accept and record `title`:

```python
    async def spawn(self, harness, model, prompt, title, *, cwd=None, detached=False):
        self.spawned.append((harness, model, prompt, title, cwd, detached))
        return {"run_id": "run-1", "status": "completed", "result": "ok"}
```

Update `test_spawn_forwards_args_and_returns_outcome` to pass and expect `title`:

```python
    _content, result = asyncio.run(
        mcp.call_tool("spawn", {"harness": "codex", "model": "gpt-5.5",
                                "prompt": "go", "title": "demo"})
    )
    assert runs.spawned == [("codex", "gpt-5.5", "go", "demo", None, False)]
    assert result["status"] == "completed" and result["result"] == "ok"
```

Then in `src/vibing_devcontainer_runtime/mcp_server.py` update the `spawn` tool:

```python
    @mcp.tool()
    async def spawn(
        harness: str, model: str, prompt: str, title: str,
        detached: bool = False, cwd: str | None = None,
    ) -> dict[str, Any]:
        """Spawn an external-subagent Delegated Run. `title` is a short UI label.
        Blocks for the result unless detached=true."""
        return await delegated_runs.spawn(harness, model, prompt, title, cwd=cwd, detached=detached)
```

(Leave `get_status`/`get_result`/`list_runs`/`instructions` for Task 3 — `test_tools_are_registered` is unchanged here.)

- [ ] **Step 6: Run both modules + mypy to verify green**

Run: `uv run pytest tests/devcontainer_runtime/test_delegated_runs.py tests/devcontainer_runtime/test_mcp_server.py -q && uv run mypy src`
Expected: PASS, mypy clean (the manager and MCP `spawn` signatures now agree).

- [ ] **Step 7: Commit**

```bash
git add src/vibing_devcontainer_runtime/delegated_runs.py src/vibing_devcontainer_runtime/mcp_server.py tests/devcontainer_runtime/test_delegated_runs.py tests/devcontainer_runtime/test_mcp_server.py
git commit -m "feat(runtime): required run title on spawn (manager + MCP tool)"
```

---

### Task 2: Title through the protocol envelope and API schema

**Files:**
- Modify: `src/vibing_protocol/messages.py`
- Modify: `src/vibing_api/api/schemas/delegated_runs.py`
- Test: `tests/api/test_runtime_intake.py`, `tests/api/test_delegated_runs_api.py`

**Interfaces:**
- Consumes: `list_runs()` items with `"title"` (Task 1).
- Produces: `DelegatedRunItem.title: str` in both the protocol envelope and the API response schema.

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_delegated_runs_api.py` (inside the existing test module; reuse its imports/fixtures). First inspect the file to match its client/fixture pattern, then add a test asserting the title round-trips to the HTTP response. Example shape (adapt to the file's existing helper for seeding live state + calling the endpoint):

```python
def test_delegated_runs_endpoint_includes_title(...):
    # seed one DelegatedRunItem(..., title="refactor auth retry") into live state,
    # GET /api/v1/devcontainers/{id}/delegated-runs
    body = resp.json()
    assert body["items"][0]["title"] == "refactor auth retry"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/api/test_delegated_runs_api.py -q`
Expected: FAIL — `DelegatedRunItem` has no `title` (validation error on the keyword, or `KeyError`/missing field in the response).

- [ ] **Step 3: Implement**

In `src/vibing_protocol/messages.py`, add to `DelegatedRunItem` (after `model`):

```python
    title: str
```

In `src/vibing_api/api/schemas/delegated_runs.py`, add to `DelegatedRunItem` (after `model`):

```python
    title: str
```

- [ ] **Step 4: Update existing `DelegatedRunItem(...)` constructions**

`title` is now required. Add `title="..."` to every `DelegatedRunItem(...)` construction in:
- `tests/api/test_runtime_intake.py:15`
- `tests/api/test_live_state.py:45`
- `tests/api/test_delegated_runs_api.py:25`

Use a descriptive value, e.g. `title="seed task"`. (Production construction at `src/vibing_devcontainer_runtime/cli.py:42` is `DelegatedRunItem(**r)` and already receives `title` from `list_runs()` — no change needed.)

- [ ] **Step 5: Run the affected suites to verify green**

Run: `uv run pytest tests/api/test_delegated_runs_api.py tests/api/test_runtime_intake.py tests/api/test_live_state.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vibing_protocol/messages.py src/vibing_api/api/schemas/delegated_runs.py tests/api
git commit -m "feat(api): carry delegated-run title through envelope and API schema"
```

---

### Task 3: MCP tool surface — list_runs, get_run, instructions

(The `spawn` title change landed in Task 1.)

**Files:**
- Modify: `src/vibing_devcontainer_runtime/mcp_server.py`
- Test: `tests/devcontainer_runtime/test_mcp_server.py`

**Interfaces:**
- Consumes: `DelegatedRunManager.list_runs()`, `.get_result(run_id)` (existing).
- Produces: MCP tools `list_runs()`, `get_run(run_id)`; removes `get_status`/`get_result` tools; sets `instructions` on the server.

- [ ] **Step 1: Update the test double and write failing tests**

In `tests/devcontainer_runtime/test_mcp_server.py`, add a `list_runs` method to `FakeDelegatedRuns` (its `spawn` and `get_result` are already present from Task 1):

```python
    def list_runs(self):
        return [{"run_id": "run-1", "title": "t", "harness": "codex",
                 "model": "gpt-5.5", "status": "running"}]
```

(`get_run` delegates to the existing `get_result`. Drop `get_status` from the fake if now unused.)

Replace `test_tools_are_registered` and add coverage:

```python
def test_tools_are_registered():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_harnesses", "spawn", "list_runs", "get_run", "stop", "await_run"} <= names
    assert "get_status" not in names and "get_result" not in names


def test_server_has_external_subagent_instructions():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    assert mcp.instructions and "external subagent" in mcp.instructions.lower()


def test_get_run_returns_status_result_error():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    _content, result = asyncio.run(mcp.call_tool("get_run", {"run_id": "run-1"}))
    assert result["status"] == "completed" and result["result"] == "ok" and "error" in result


def test_list_runs_tool_returns_titles():
    mcp = build_mcp_server(FakeExecutor(), _descriptors_map(), FakeDelegatedRuns())
    _content, result = asyncio.run(mcp.call_tool("list_runs", {}))
    items = result["result"] if isinstance(result, dict) and "result" in result else result
    assert items[0]["title"] == "t"
```

- [ ] **Step 2: Run to verify failures**

Run: `uv run pytest tests/devcontainer_runtime/test_mcp_server.py -q`
Expected: FAIL — `get_run`/`list_runs` tools missing, `instructions` unset, `get_status`/`get_result` still registered.

- [ ] **Step 3: Implement the server changes**

In `src/vibing_devcontainer_runtime/mcp_server.py`, define the instructions constant above `build_mcp_server`:

```python
_INSTRUCTIONS = """\
This server provides EXTERNAL SUBAGENTS: full coding-harness runs you dispatch work to,
complementing the in-process Task subagents of subagent-driven-development. When the user
says "use external subagent", dispatch the work here.

Dispatch protocol:
1. spawn(harness, model, prompt, title, detached=true) -> run_id. `title` is a short human
   label shown in the UI.
2. Run `vibing delegated wait <run_id>` as a BACKGROUND shell command; its completion
   auto-wakes you with the result. Do not poll get_run in a loop.
3. get_run(run_id) -> status + result + error. list_runs() -> all runs. stop(run_id) cancels.

Model rule of thumb:
- cursor  -> composer-2.5 (or latest Composer): fast, cheap, good default.
- codex   -> gpt-5.5 (or latest GPT): autonomous CLI coding.
See docs/external-subagent-guide.md for deeper task -> model routing.
"""
```

Pass it to the constructor:

```python
    mcp = FastMCP(
        "vibing-harness",
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
        instructions=_INSTRUCTIONS,
    )
```

Replace the `get_status`/`get_result` tools with `list_runs` and `get_run` (the `spawn` tool already carries `title` from Task 1):

```python
    @mcp.tool()
    def list_runs() -> list[dict[str, Any]]:
        """List dispatched Delegated Runs (run_id, title, harness, model, status)."""
        return delegated_runs.list_runs()

    @mcp.tool()
    def get_run(run_id: str) -> dict[str, Any]:
        """Get a Delegated Run's status, result, and error."""
        return delegated_runs.get_result(run_id)
```

Delete the old `get_status` and `get_result` `@mcp.tool()` definitions. Leave `await_run`, `stop`, `list_harnesses` unchanged.

- [ ] **Step 4: Run to verify green**

Run: `uv run pytest tests/devcontainer_runtime/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vibing_devcontainer_runtime/mcp_server.py tests/devcontainer_runtime/test_mcp_server.py
git commit -m "feat(mcp): title param, list_runs+get_run tools, external-subagent instructions"
```

---

### Task 4: Harness/model guide doc + docs coherence

**Files:**
- Create: `docs/external-subagent-guide.md`
- Modify: `src/vibing_devcontainer_runtime/CLAUDE.md`

No code; no test cycle. This task's gate is doc accuracy (model ids match `cursor-agent models`; rule of thumb matches the instructions string).

- [ ] **Step 1: Write the guide**

Create `docs/external-subagent-guide.md`:

```markdown
# External Subagent Routing Guide

The `vibing-harness` MCP server dispatches work to **external subagents** — full
coding-harness runs (ADR-0013). This guide says which harness + model to pick.

## Rule of thumb (use this first)

- **cursor → `composer-2.5`** (or latest Composer): fast, cheap, strong default.
- **codex → `gpt-5.5`** (or latest GPT): autonomous CLI coding.

## Environment pins

- **codex** uses ChatGPT-account auth; its working model is **`gpt-5.5`**. The
  `-codex`-suffixed models (e.g. `gpt-5.2-codex`) are **API-key-only** and are rejected
  on a ChatGPT plan.
- **cursor** is a multi-model router. Run `cursor-agent models` for the live menu
  (Claude Opus/Sonnet/Fable, GPT-5.x, Gemini 3.x, Grok, Kimi, GLM, Composer); many ids
  carry effort/thinking/fast suffixes.

## Decision table (secondary — reach past the rule of thumb only when it matters)

| Task | Harness: model |
|---|---|
| Deep architecture / planning / hard debugging | cursor: `claude-opus-4-8-thinking-high` |
| Long-horizon autonomous multi-file refactor (CLI) | codex: `gpt-5.5` |
| Hardest large migration / multi-day run | cursor: `claude-fable-5-thinking-high` |
| Balanced day-to-day coding / test writing | cursor: `claude-4.6-sonnet-medium` |
| Frontend / UI | cursor: `claude-4.6-sonnet-medium` |
| Huge-context whole-repo analysis | cursor: `gemini-3.1-pro` |
| Fast inner-loop edits, low latency | cursor: `composer-2.5` |
| Bulk mechanical edits / classification | cursor: `gpt-5.4-mini-low` |

**Family notes (conservative, durable patterns):** Opus = deep reasoning, architecture,
review. Sonnet = balanced daily driver + frontend. Fable 5 = Anthropic's *most capable*
tier (not cheap — the cheap Claude is Haiku). GPT-5.x / codex = long-horizon CLI autonomy.
Gemini Pro = huge context; Flash = fast/cheap. Composer = low-latency fast loop, not deep
reasoning. mini/nano/flash tiers = bulk mechanical work only.

## Adding a new harness to this guide

When a harness is added to `vibing_harness`:

1. **Probe live.** Run the harness's own model-list command (e.g. `cursor-agent models`)
   and one trivial `spawn` per candidate to confirm what actually works in the target auth
   mode. Document auth-gated exclusions (as with codex `-codex` models).
2. **Add a rule-of-thumb line** (harness → best default model) above.
3. **Add decision-table rows** for the harness; note family strengths conservatively.
4. **Update the server `instructions`** rule-of-thumb list in
   `src/vibing_devcontainer_runtime/mcp_server.py` if the default choice changes.
```

- [ ] **Step 2: Validate the cursor model ids against the live menu**

Run: `cursor-agent models | grep -E 'composer-2.5|claude-opus-4-8-thinking-high|claude-fable-5-thinking-high|claude-4.6-sonnet-medium|gemini-3.1-pro|gpt-5.4-mini-low'`
Expected: each id appears in the output. If an id is absent, replace it with the closest live id and update the table. (codex `gpt-5.5` was confirmed live separately.)

- [ ] **Step 3: Update runtime CLAUDE.md**

In `src/vibing_devcontainer_runtime/CLAUDE.md`, update the `mcp_server.py` bullet: tool list becomes `list_harnesses`/`spawn`/`list_runs`/`get_run`/`await_run`/`stop` (replacing `get_status`/`get_result` with `get_run`, adding `list_runs`), and add a sentence: the server carries `instructions` framing these as *external subagents* and the rule-of-thumb model routing (see `docs/external-subagent-guide.md`).

- [ ] **Step 4: Commit**

```bash
git add docs/external-subagent-guide.md src/vibing_devcontainer_runtime/CLAUDE.md
git commit -m "docs: external-subagent routing guide + runtime CLAUDE.md coherence"
```

---

### Task 5: Frontend — render title in the rail + mock data

**Files:**
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/components/RailActivity.tsx`
- Modify: `apps/web/src/mock/state/seeds.ts`
- Test: `apps/web/src/components/__tests__/RailActivity.test.tsx`

**Interfaces:**
- Consumes: API `DelegatedRun` items with `title`.
- Produces: `DelegatedRun.title: string`; rail item shows the title as the primary label.

- [ ] **Step 1: Update the unit test (failing)**

In `apps/web/src/components/__tests__/RailActivity.test.tsx`, give the fixtures titles and assert the title renders:

```ts
const runs: DelegatedRun[] = [
  { run_id: 'run-9', title: 'refactor auth retry', harness: 'claude-code', model: 'opus-4.8', status: 'running', result: null, error: null, started_at: '2024-01-15T10:20:00.000Z' },
  { run_id: 'run-3', title: 'add parser tests', harness: 'cursor', model: 'auto', status: 'completed', result: 'done', error: null, started_at: '2024-01-15T09:55:00.000Z' },
]
```

Replace the first assertion block:

```ts
    await waitFor(() => expect(screen.getByText('refactor auth retry')).toBeTruthy())
    expect(screen.getByText('run-9 · claude-code · opus-4.8')).toBeTruthy()
    expect(screen.queryByText('add parser tests')).toBeNull()
    expect(mockRuns).toHaveBeenCalledWith('dc-1')
```

- [ ] **Step 2: Run to verify it fails**

Run (from `apps/web`): `pnpm test -- RailActivity`
Expected: FAIL — `title` missing on the type / `refactor auth retry` not found.

- [ ] **Step 3: Add the type field**

In `apps/web/src/lib/api/types.ts`, add to `DelegatedRun` (after `model`):

```ts
  title: string
```

- [ ] **Step 4: Render the title in `RailActivity.tsx`**

Replace the `<li>` body so the title is the primary label and `run_id · harness · model` is the subtitle:

```tsx
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent" />
            <span className="text-[12px] font-medium leading-tight text-text">{run.title}</span>
          </div>
          <div className="pl-3 font-mono text-[11px] leading-tight text-text-subtle">{run.run_id} · {run.harness} · {run.model}</div>
```

- [ ] **Step 5: Add titles to the mock seeds**

In `apps/web/src/mock/state/seeds.ts`, add a `title` to **every** entry in `seedDelegatedRuns['dc-seed-0001']` (the type now requires it). Suggested titles (running ones must read well in the rail):

```ts
  { run_id: 'run-9', title: 'refactor auth retry', harness: 'claude-code', model: 'opus-4.8', status: 'running', ... },
  { run_id: 'run-8', title: 'wire settings page', harness: 'cursor', model: 'auto', status: 'running', ... },
  { run_id: 'run-7', title: 'migrate config loader', harness: 'codex', model: 'gpt-5-codex', status: 'running', ... },
  { run_id: 'run-6', title: 'add e2e for rail', harness: 'claude-code', model: 'opus-4.8', status: 'running', ... },
  { run_id: 'run-4', title: 'fix flaky test', harness: 'codex', model: 'gpt-5-codex', status: 'running', ... },
  { run_id: 'run-3', title: 'refactor auth module', harness: 'claude-code', model: 'opus-4.8', status: 'completed', ... },
  { run_id: 'run-2', title: 'install deps', harness: 'cursor', model: 'auto', status: 'failed', ... },
  { run_id: 'run-1', title: 'spike caching', harness: 'codex', model: 'gpt-5-codex', status: 'stopped', ... },
  { run_id: 'run-0', title: 'add parser unit tests', harness: 'claude-code', model: 'opus-4.8', status: 'completed', ... },
```

(Keep each entry's existing `result`/`error`/`started_at` fields; only insert `title`.)

- [ ] **Step 6: Run unit tests + build to verify green**

Run (from `apps/web`): `pnpm test -- RailActivity && pnpm build`
Expected: PASS and a clean type-checked build (build catches any other `DelegatedRun` construction now missing `title`; fix any the compiler flags).

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/lib/api/types.ts apps/web/src/components/RailActivity.tsx apps/web/src/mock/state/seeds.ts apps/web/src/components/__tests__/RailActivity.test.tsx
git commit -m "feat(web): show delegated-run title in the activity rail"
```

---

### Task 6: Frontend e2e — title visible in the rail

**Files:**
- Modify: `apps/web/e2e/devcontainer-detail.spec.ts`

**Interfaces:**
- Consumes: the MSW seed titles (Task 5) on `dc-seed-0001`.

- [ ] **Step 1: Add the e2e test**

Append to `apps/web/e2e/devcontainer-detail.spec.ts`:

```ts
test('active runs rail shows delegated-run titles', async ({ page }) => {
  await page.goto('/devcontainers/dc-seed-0001') // running; has running delegated runs
  const rail = page.getByRole('complementary').filter({ hasText: 'Active runs' })
  await expect(page.getByText('refactor auth retry')).toBeVisible()
})
```

If the right rail is not a `complementary` landmark, target the heading instead:
`await expect(page.getByText('Active runs')).toBeVisible()` then assert the title text. Adjust the selector to whatever `AppShell`/`RailActivity` actually renders (verify by reading those files), keeping the title-visibility assertion.

- [ ] **Step 2: Run the e2e suite**

Run (from `apps/web`): `pnpm e2e devcontainer-detail`
Expected: PASS — `refactor auth retry` is visible in the rail for the running devcontainer.

- [ ] **Step 3: Commit**

```bash
git add apps/web/e2e/devcontainer-detail.spec.ts
git commit -m "test(web): e2e asserts delegated-run title in the activity rail"
```

---

## Final verification (after all tasks)

- [ ] Python: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src && uv run pytest -q`
- [ ] Frontend (from `apps/web`): `pnpm test && pnpm build && pnpm e2e`
- [ ] Manual smoke (optional, harnesses authenticated): `spawn(harness="cursor", model="composer-2.5", prompt="reply OK", title="smoke", detached=true)` → `vibing delegated wait <run_id>` in background → wakes with the result; `list_runs()` shows the title.
