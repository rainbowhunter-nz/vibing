# vibing-host-runtime

Host Runtime Worker for the Vibing MVP.

Connects to the Control Plane over a single WebSocket (ADR-0003), registers as the one host worker, and serially runs Devcontainer lifecycle Commands by shelling out to the official `devcontainer` CLI.

## Usage

```bash
cd packages/host_runtime
uv run vibing-host-runtime serve
```

| Flag | Default | Purpose |
|---|---|---|
| `--control-plane-url` | `ws://127.0.0.1:8000/api/v1/runtime/ws` | Control Plane runtime WebSocket (host-side: `127.0.0.1`) |
| `--devcontainer-cli` | `devcontainer` | Dev Container CLI binary name or path |
| `--agent-control-plane-url` | `ws://host.docker.internal:8000/api/v1/runtime/agent/ws` | Agent WebSocket URL injected into the container (`host.docker.internal`, not `127.0.0.1`) |

## Auto-launch of Devcontainer Runtime Agent

After a successful `devcontainer up`, the worker automatically launches the Devcontainer Runtime Agent inside the container via a detached `devcontainer exec`:

```
devcontainer exec --workspace-folder <path> -- bash -lc \
  'nohup vibing-devcontainer-runtime serve \
    --control-plane-url <agent-url> \
    --devcontainer-id <id> \
    >/tmp/vibing-agent.log 2>&1 &'
```

The `nohup ... &` backgrounds the agent inside the container so `exec` returns immediately — the worker's serial queue is not blocked.

**Prerequisite:** `vibing-devcontainer-runtime` must be pre-installed in the Devcontainer image. The worker does not install it.

**Why two different URLs?** The worker runs on the host and reaches the Control Plane at `127.0.0.1`. The agent runs *inside* the container and must use `host.docker.internal` to reach the host. Use `--agent-control-plane-url` to override the agent-side URL.

**Best-effort:** launch failure (non-zero exit, binary missing) logs a `WARNING` only and leaves the `devcontainer_started` event intact. A missing agent surfaces later as `409` on `start_agent_session`, mirroring the missing-host-worker case.

## Agent WebSocket endpoint

The agent connects to `/api/v1/runtime/agent/ws` (ADR-0004), distinct from the host worker's `/api/v1/runtime/ws`. The agent registers with `source="devcontainer_runtime_agent"` and its `devcontainer_id`.

## Architecture

See ADR-0003 (star topology) and ADR-0004 (agent endpoint, agent launch) in `docs/adr/`.
