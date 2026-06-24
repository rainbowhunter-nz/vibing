# Delegated-Run Completion Wakes the Main Harness

## Problem

When the main coding harness (interactive Claude Code) spawns a **detached** Delegated Run
via the MCP server (`spawn(detached=true)`), it gets a `run_id` back immediately and the run
executes in-container. To learn the outcome the harness must keep calling `get_status` /
`get_result` — i.e. poll. We want the harness to instead return to idle (the user can keep
chatting, including asking "is the run done?") and be **automatically woken** when the run
finishes, so it can act on the result without polling.

## Constraints (verified against Claude Code behavior)

- Only three things wake an idle interactive Claude Code session: a **background Bash command
  finishing**, a **background subagent returning**, or a **channel** notification (an external
  MCP-push feature, research-preview).
- The background-task wake is **harness-internal**: the harness only re-activates from children
  it launched itself. There is **no external trigger** an outside process (the runtime, the
  delegated run) can fire to wake the agent — except channels.
- MCP tool calls **cannot** be backgrounded in the interactive TUI; only Bash and subagents can.

The lightest design that rides the only no-dependency wake mechanism: have the harness launch a
**background Bash command that blocks until the run finishes**. When it returns, the harness
wakes with the result. We just need a blocking wait the background command can call.

Rejected alternatives: a **channel** (whole second MCP server + research-preview flag + org
policy — overkill); **Control-Plane involvement** (the CP already observes runs via ADR-0016,
but routing the wake through it adds a component the user explicitly wants kept out — this is a
pure runtime/MCP feature); launching the harness itself as a background Bash job (bypasses the
in-container `DelegatedRunManager`: the concurrency cap, auth, descriptor argv, CP observation).

## Flow

1. Harness calls `spawn(detached=true)` → `run_id`, returns to idle.
2. Harness runs `vibing delegated wait <run_id>` as a **background Bash command**.
3. While idle the user chats freely; "is run-3 done?" is answered by the existing `get_status`.
4. Run reaches a terminal state (`completed` / `failed` / `stopped`) → the background command
   returns → Claude Code auto-wakes the main agent with the result. No CP, no channel, no
   research-preview dependency.

## Components

Three small additions. `spawn`, `get_status`, `get_result`, `stop`, and the entire Control-Plane
/ ADR-0016 observation path are **untouched**.

### 1. `DelegatedRunManager.await_run(run_id, timeout)` — `delegated_runs.py`

Backs the blocking wait.

- Add `done: asyncio.Event` to `_Run` (`field(default_factory=asyncio.Event)`).
- Set `run.done` on **every** terminal transition. Set it in `_await_run` via a `finally`
  guard (`if run.status != "running": run.done.set()`) so the completed / failed / cancelled
  (→ stopped) paths all fire it, and in `stop()` for the already-terminal case.
- `await_run`:
  - Unknown `run_id` → `KeyError` (consistent with `_get`; surfaces as an MCP error).
  - Already terminal → return the `get_result` payload immediately.
  - Otherwise `await asyncio.wait_for(run.done.wait(), timeout)`; on `TimeoutError` return
    `{"run_id", "status": "running", "timed_out": True}`.
  - On wake → return the `get_result` payload (`run_id`, `status`, `result`, `error`).

The bounded `timeout` keeps the long-poll HTTP request from hanging forever; the caller
re-issues on `timed_out`.

### 2. `await_run` MCP tool — `mcp_server.py`

```python
@mcp.tool()
async def await_run(run_id: str, timeout_seconds: float = 25.0) -> dict[str, Any]:
    """Block until a detached Delegated Run finishes; return its result. Re-call if timed_out."""
    return await delegated_runs.await_run(run_id, timeout=timeout_seconds)
```

Pure MCP; usable by any MCP client, not just the CLI.

### 3. `vibing delegated wait <run_id>` CLI — `src/vibing_cli/delegated.py` (new)

The backgroundable shim the harness runs. A thin streamable-HTTP MCP client (via the `mcp`
client SDK, already a dependency) that:

- Connects to the runtime MCP server. URL from `--mcp-url` / `VIBING_MCP_URL`, default
  `http://127.0.0.1:8848/mcp` (inside the devcontainer use `http://host.docker.internal:8848/mcp`).
- Calls `await_run(run_id)` in a loop, re-issuing while the response is `timed_out`, until a
  terminal status.
- Prints a concise result (status + result text, or error) and exits **0** when the wait
  resolved to a terminal state; non-zero only when the wait itself failed (unknown run id,
  server unreachable). Either way the harness wakes with the output.

Mounted as a top-level `delegated` Typer sub-app in `vibing_cli/__init__.py`.

**Alternative (documented, not built):** a background *subagent* that calls the `await_run`
MCP tool directly needs no CLI, but spins a whole agent context just to block — heavier and
costlier than the Bash shim.

## Edge cases

- Already-terminal run when waited → immediate return.
- Unknown `run_id` → CLI exits non-zero with a clear message; harness wakes and reacts.
- `stop` during the wait → run becomes `stopped`, `done` fires, wait returns `stopped`.
- Runtime restart loses the run (runs are in-memory, ADR-0013) → `await_run` errors → CLI exits
  non-zero → harness wakes and reacts.
- Arbitrarily long run → CLI re-loops past each bounded `timeout`.
- Concurrent waiters on one run → `asyncio.Event` supports multiple awaiters.

## Testing

- `tests/devcontainer_runtime/test_delegated_runs.py`: `await_run` returns on
  completion / failure / stop; returns immediately when already terminal; `timed_out` path;
  unknown id raises. Reuse the existing `ScriptedProcess` + gate harness.
- `tests/devcontainer_runtime/test_mcp_server.py`: `await_run` registered and forwards args
  (extend `FakeDelegatedRuns`).
- `tests/cli/`: `vibing delegated wait` loops past `timed_out`, prints terminal result, exit
  codes correct — against a fake MCP endpoint / stubbed client.

## Docs coherence

- `src/vibing_devcontainer_runtime/CLAUDE.md`: add `await_run` to the `mcp_server.py` tool list.
- `src/vibing_cli/CLAUDE.md`: document `vibing delegated wait` and the `VIBING_MCP_URL` env var.
- New ADR: the "delegated-run completion wakes the main harness via a background-shell blocking
  wait" pattern, and why not channels / not the Control Plane. Add the index entry.
