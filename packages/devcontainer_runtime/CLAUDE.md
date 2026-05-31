# packages/devcontainer_runtime — Devcontainer Runtime Agent (`vibing-devcontainer-runtime`)

Runs **inside** the container and owns the **agent-session lifecycle**: launches Claude Code,
emits structured RuntimeEvents (started/completed/failed). Receives devcontainer-side Commands
from the Control Plane and emits RuntimeEvents back. Has a `serve` CLI that connects to
`/runtime/agent/ws`, registers as `devcontainer_runtime_agent` with a `devcontainer_id`, and
handles `start_agent_session` by running Claude as a background task. Depends on
`packages/protocol` and `packages/runtime_client`. Read the root `CONTEXT.md`.

Use `uv` only — never hand-edit `pyproject.toml`. Tests: `uv run pytest -q`.

## Where things live

- `src/vibing_devcontainer_runtime/__init__.py` — public surface; re-exports the symbols below.
- `src/vibing_devcontainer_runtime/cli.py` — `vibing-devcontainer-runtime` entry point: Typer `cli`, `serve` command with `--control-plane-url` and `--devcontainer-id` options; wires `AgentCommandHandler(ClaudeCodeRunner()).handle` and runs `RuntimeChannelClient`. Default URL: `ws://host.docker.internal:8000/api/v1/runtime/agent/ws`.
- `src/vibing_devcontainer_runtime/claude_runner.py` — `ClaudeCodeRunner`: runs `claude -p "<prompt>" --output-format json --permission-mode bypassPermissions` via injectable `Runner`; `start(prompt) -> ClaudeProcess` returns a handle; `run(prompt)` is a convenience `start().wait()`. `ClaudeProcess.wait()` returns `ClaudeSuccess`/`ClaudeFailure`; `terminate()` sends SIGTERM → 5s grace → SIGKILL. `bypassPermissions` is intentional — approval detection deferred to future `--permission-prompt-tool` work.
- `src/vibing_devcontainer_runtime/command_handler.py` — `AgentCommandHandler`: on `start_agent_session` emits `agent_session_started`, calls `runner.start()`, stores the `ClaudeProcess` handle per session, schedules `process.wait()` as a background task; emits `session_completed` or `session_failed` when done. On `stop_agent_session`: cancels the in-flight bg task, calls `process.terminate()` (SIGTERM→grace→SIGKILL), emits `session_stopped`. If no running process, still emits `session_stopped` (idempotent). Race allowed: `session_completed`/`session_failed` may fire before cancel — at least one terminal event is guaranteed (ADR-0004).
- `src/vibing_devcontainer_runtime/runtime.py` — `DEVCONTAINER_COMMAND_TYPES` (agent-session start/stop, send_user_input, resolve_approval), the `DevcontainerRuntime` Protocol, and the `DevcontainerRuntimeAgent` skeleton.

## Conventions

- Command/event shapes come from `vibing-protocol` — never redefine them here.
- `DEVCONTAINER_COMMAND_TYPES` must stay a subset of `protocol`'s `CommandType`.
- This package emits events; the Control Plane reducer (`apps/api`) is the one that projects them.
