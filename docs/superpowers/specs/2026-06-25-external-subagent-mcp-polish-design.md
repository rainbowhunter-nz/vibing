# External-Subagent MCP Server Polish

## Problem

The delegation MCP server (`vibing-harness`) works, but it isn't yet a clean "external
subagent" surface for the main agent:

- Runs are labelled only `run-1`, `run-2`. No human-meaningful name reaches the UI.
- `list_runs()` exists on the manager but is **not** an MCP tool — after dispatching several
  runs the agent cannot enumerate them; it must remember every `run_id` itself.
- `get_status` and `get_result` overlap (status-only vs status+result+error) — two tools where
  one suffices.
- Nothing tells the main agent what this server is *for*, when to reach for it ("use external
  subagent"), how to dispatch+wake, or which harness/model to pick.

Goal: make the server a straightforward external-subagent dispatcher that extends the
superpowers `subagent-driven-development` model — in-process Task subagents plus these
out-of-process harness runs.

## Scope

In: required run title; `list_runs` MCP tool; merge `get_status`+`get_result` → `get_run`;
server `instructions`; a harness/model guide doc. Out: the wake mechanism (ADR-0021, done),
auth/install (Control Plane, ADR-0019), run durability (ADR-0013).

## Design

### 1. Required run title

`spawn` gains a **required** `title: str` — a short human label (e.g. `"refactor auth retry"`).

- Stored on `_Run` (`title: str`).
- Surfaced in `list_runs()` payload → the `delegated_runs` envelope → Control Plane / web UI.
- The `run-N` `run_id` is unchanged: machine handle and human label stay separate.
- Core payloads (`spawn`, `get_run`, `await_run`) need not echo the title.

### 2. Tool surface (6 tools, each pulls its weight)

| Tool | Change |
|---|---|
| `list_harnesses()` | unchanged |
| `spawn(harness, model, prompt, title, detached=False, cwd=None)` | **adds `title`** |
| `list_runs()` | **new MCP tool** — `run_id`, `title`, `harness`, `model`, `status` per run |
| `get_run(run_id)` | **merges** `get_status`+`get_result`; returns status + result + error |
| `await_run(run_id, timeout_seconds=25.0)` | unchanged |
| `stop(run_id)` | unchanged |

`get_status` and `get_result` MCP tools are **removed** (replaced by `get_run`). The manager keeps
`get_result` internally (used by `await_run`); `get_status` manager method is removed if unused.

### 3. Server `instructions` (lean)

Set `instructions=` on the FastMCP server. The MCP client surfaces it to the main agent
automatically. Three short parts:

1. **What** — "This server provides *external subagents*: full coding-harness runs you dispatch
   work to, complementing in-process Task subagents. When the user says **'use external
   subagent'**, dispatch work here."
2. **How** — dispatch protocol:
   - `spawn(harness, model, prompt, title, detached=true)` → `run_id`.
   - Run `vibing delegated wait <run_id>` as a **background shell command**; its completion
     auto-wakes you with the result (ADR-0021). Do not poll.
   - `get_run(run_id)` for the result; `list_runs()` to see all dispatched runs; `stop(run_id)`
     to cancel.
3. **Which** — the rule of thumb (below) + a pointer to the guide doc for deeper routing.

Keep `instructions` condensed — the full table lives in the doc, not in every agent's context.

### 4. Harness/model guide doc

New doc `docs/external-subagent-guide.md`. Leads with the rule of thumb; the table is secondary
reference.

**Rule of thumb**
- **cursor** → `composer-2.5` (or latest Composer) — fast, cheap, good default.
- **codex** → `gpt-5.5` (or latest GPT) — autonomous CLI coding.

**Empirical pins (this environment)**
- codex uses ChatGPT-account auth; its working model is **`gpt-5.5`**. The `-codex`-suffixed
  models (e.g. `gpt-5.2-codex`) are **API-key-only** and rejected on a ChatGPT plan.
- cursor-agent is a multi-model router; `cursor-agent models` lists the live menu (Claude
  Opus/Sonnet/Fable, GPT-5.x, Gemini 3.x, Grok, Kimi, GLM, Composer), many with
  effort/thinking/fast suffixes.

**Decision table (secondary — use the rule of thumb first)**

| Task | Harness + model | Effort |
|---|---|---|
| Deep architecture / planning / hard debugging | cursor: `claude-opus-4-8` | high |
| Long-horizon autonomous multi-file refactor (CLI) | codex: `gpt-5.5` | high |
| Hardest large migration / multi-day run | cursor: `claude-fable-5` (top tier) | high |
| Balanced day-to-day coding / tests | cursor: `claude-4.6-sonnet` | medium |
| Frontend / UI | cursor: `claude-4.6-sonnet` | medium |
| Huge-context whole-repo analysis | cursor: `gemini-3.1-pro` | medium/high |
| Fast inner-loop edits, low latency | cursor: `composer-2.5` | low |
| Bulk mechanical edits / classification | cursor: a mini/nano/flash tier | low |

Family notes (conservative, durable patterns): Opus = deep reasoning/architecture/review;
Sonnet = balanced daily driver + frontend; Fable 5 = Anthropic's *most capable* tier (not cheap —
cheap Claude is Haiku); GPT-5.x / codex = long-horizon CLI autonomy; Gemini Pro = huge context,
Flash = fast/cheap; Composer = low-latency fast loop, not deep reasoning.

**How to add a new harness to this guide (future)**

When a new harness is added to `vibing_harness`:
1. Probe its live model menu (the harness's own list command, e.g. `cursor-agent models`) and run
   one trivial `spawn` per candidate to confirm what actually works in the target auth mode —
   document any auth-gated exclusions (as with codex `-codex` models).
2. Add a one-line **rule of thumb** entry (harness → best default model).
3. Add the harness's rows to the decision table; note family strengths conservatively.
4. Update the server `instructions` rule-of-thumb list if the new harness changes the default
   choice.

## Components touched

- `delegated_runs.py`: `_Run.title`; `spawn(..., title)`; `list_runs()` includes `title`; drop
  unused `get_status` method if no longer referenced.
- `mcp_server.py`: `spawn` adds `title`; add `list_runs` tool; replace `get_status`/`get_result`
  with `get_run`; add `instructions=` to `FastMCP(...)`.
- `docs/external-subagent-guide.md`: new.
- Untouched: `await_run`, the CLI waiter, the wake path, CP observation.

## Testing

- `tests/devcontainer_runtime/test_delegated_runs.py`: `spawn` requires/stores `title`;
  `list_runs` includes `title`.
- `tests/devcontainer_runtime/test_mcp_server.py`: `spawn` forwards `title`; `list_runs`
  registered + forwards; `get_run` registered + returns status+result+error; `get_status`/
  `get_result` no longer registered; `instructions` set on the server.

## Docs coherence

- `src/vibing_devcontainer_runtime/CLAUDE.md`: update the `mcp_server.py` tool list (`list_runs`,
  `get_run` replacing `get_status`/`get_result`) and note the server `instructions`.
- `docs/external-subagent-guide.md`: the guide (new), linked from the runtime CLAUDE.md.
- ADR: not required — no new architectural decision beyond ADR-0013/0021; this is a surface
  polish. (Add one only if review judges the "external subagent" framing ADR-worthy.)
