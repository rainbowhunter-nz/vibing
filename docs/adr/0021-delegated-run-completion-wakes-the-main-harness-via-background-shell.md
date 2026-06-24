# Delegated-run completion wakes the main harness via a background-shell blocking wait

The main harness (interactive Claude Code) spawns detached Delegated Runs (ADR-0011/0013) and
needed to poll `get_status`/`get_result` to learn the outcome. We want the harness to idle (the
user keeps interacting) and resume automatically when a run finishes.

Only three things wake an idle interactive Claude Code session: a background Bash command
finishing, a background subagent returning, or a channel notification. The background-task wake
is harness-internal — the harness only re-activates from children it launched; no external
process can trigger it. So we ride that mechanism: the harness runs `vibing delegated wait
<run_id>` as a background Bash command, which long-polls a new `await_run` MCP tool until the run
is terminal; its exit wakes the harness with the result.

`await_run` is backed by a per-run terminal `asyncio.Event` in `DelegatedRunManager` and a
bounded-timeout long-poll (the CLI re-issues on timeout). MCP tool calls cannot be backgrounded
in the TUI, so the backgroundable shim is a CLI (`vibing delegated wait`), a thin streamable-HTTP
MCP client. A background subagent calling `await_run` directly is an alternative but spins a whole
agent context to block.

Rejected: **channels** (a second MCP server + research-preview flag + org policy — overkill for
this); **Control-Plane involvement** (the CP already observes runs via ADR-0016, but this is a
pure runtime/MCP concern and routing the wake through the CP adds coupling); launching the harness
itself as a background Bash job (bypasses `DelegatedRunManager`'s cap, auth, descriptor argv, and
CP observation).

Consequences: the wake only fires while the harness terminal is open and idle (close it → missed,
re-check via `get_status` on return). `spawn`/`get_status`/`get_result`/`stop` and the ADR-0016
observation path are unchanged.

Status: accepted
