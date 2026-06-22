# vibing_devcontainer_runtime

In-container companion process. Reduces friction of using coding harnesses — installs/authenticates managed harnesses from credentials the Control Plane delivers, reports Harness Status, and hosts the MCP delegation server for Delegated Runs.

## Files

- `cli.py`: `vibing devcontainer-runtime --devcontainer-id ...`. Starts runtime_client + MCP server concurrently.
- `preflight.py`: `vibing runtime preflight --control-plane-url <ws-url>` — HTTP `GET` of the control-plane health endpoint (derived from the WS URL: `ws`→`http`, `/runtime/agent/ws`→`/api/v1/health`). Exit 0 if reachable, else exit 1 with a `PREFLIGHT FAILED:` line. Run inside the container during inject's bootstrap half, before the runtime is spawned.
- `runtime_client.py`: WebSocket client that connects to `/runtime/agent/ws`, sends `register` + `harness_status`, and receives `command` envelopes.
- `command_handler.py`: dispatches incoming Commands; routes `authenticate_harness` to `harness_manager`.
- `harness_manager.py`: drives harness adapters for `authenticate_harness` and status reporting (ADR-0012).
- `harness/`: per-harness adapters (`base` contract, `codex`, `cursor`), `process` subprocess seam, `registry.build_adapters`. The only place pinned to each harness's CLI flags + credential path.
- `delegated_runs.py`: `DelegatedRunManager` — concurrent capped unattended runs; manages lifecycle of spawned harness processes.
- `mcp_server.py`: `build_mcp_server` — streamable-HTTP MCP server (`list_harnesses`/`spawn`/`get_status`/`get_result`/`stop`) the main harness calls (ADR-0011, ADR-0013).

## Context

- Launched detached by the Control Plane's injector **only after** its bootstrap half (`uv tool install` + a `vibing runtime preflight` reachability probe) succeeds; the install, the preflight result, and the runtime's stdout/stderr are all teed to `/tmp/vibing-runtime.log`, and its PID recorded in `/tmp/vibing-runtime.pid` for `stop-runtime`.
- Connects out to Control Plane `/runtime/agent/ws` as the Devcontainer Runtime.
- On connect: sends `register`, then immediately sends `harness_status` for each managed harness.
- On `install_harness`/`authenticate_harness` Command: installs/authenticates the harness, then reports the **full** `harness_status` list (not just the touched harness — the Control Plane cache replaces wholesale, so a single-item report would drop the others).
- No agent sessions, no Claude runner, no transcript/stream normalizer.
- MCP server default: `127.0.0.1:8848`. Main harness (Claude Code) is the MCP client.
- Tests: `tests/devcontainer_runtime`.
