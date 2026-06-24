# vibing_devcontainer_runtime

In-container companion process. **Delegation-only** — hosts the MCP delegation server for Delegated Runs and checks managed-harness status locally for `list_harnesses`. Harness install/authenticate/status-for-display is the Control Plane's job, not the runtime's (ADR-0019).

## Files

- `cli.py`: `vibing devcontainer-runtime --devcontainer-id ...`. Starts runtime_client + MCP server concurrently.
- `preflight.py`: `vibing runtime preflight --control-plane-url <ws-url>` — HTTP `GET` of the control-plane health endpoint (derived from the WS URL: `ws`→`http`, `/runtime/agent/ws`→`/api/v1/health`). Exit 0 if reachable, else exit 1 with a `PREFLIGHT FAILED:` line. Run inside the container during inject's bootstrap half, before the runtime is spawned.
- `runtime_client.py`: WebSocket client that connects to `/runtime/agent/ws` and sends `register` + `delegated_runs`. **Outbound-only** — receives no Commands.
- `local_executor.py`: `LocalExecutor` — the in-container `vibing_harness.Executor` impl (local subprocess `run`, direct `read`/`write`). Used for `list_harnesses` status checks and spawn.
- `delegated_runs.py`: `DelegatedRunManager` — concurrent capped unattended runs; manages lifecycle of spawned harness processes (spawn argv/env from `vibing_harness`).
- `mcp_server.py`: `build_mcp_server` — streamable-HTTP MCP server (`list_harnesses`/`spawn`/`get_status`/`get_result`/`await_run`/`stop`) the main harness calls (ADR-0011, ADR-0013). `list_harnesses` reads `vibing_harness` descriptors via `LocalExecutor`. `await_run` long-polls until a detached run is terminal (`completed`/`failed`/`stopped`) so the main harness can be woken by a background-shell waiter instead of polling.

## Context

- Launched detached by the Control Plane's injector **only after** its bootstrap half (`uv tool install` + a `vibing runtime preflight` reachability probe) succeeds; the install, the preflight result, and the runtime's stdout/stderr are all teed to `/tmp/vibing-runtime.log`, and its PID recorded in `/tmp/vibing-runtime.pid` for `stop-runtime`.
- Connects out to Control Plane `/runtime/agent/ws` as the Devcontainer Runtime; sends `register` on connect, then `delegated_runs` snapshots on run state changes (ADR-0016).
- Does **not** install/authenticate harnesses or push `harness_status` — the Control Plane writes credentials and computes status via `devcontainer exec` (ADR-0019). The runtime's only harness reads are local status checks for `list_harnesses` and cred-file reads for `cursor` spawn env.
- No agent sessions, no Claude runner, no transcript/stream normalizer.
- MCP server default: `127.0.0.1:8848`. Main harness (Claude Code) is the MCP client.
- Tests: `tests/devcontainer_runtime`.
