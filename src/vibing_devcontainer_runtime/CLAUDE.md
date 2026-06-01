# vibing_devcontainer_runtime

Agent worker. Runs inside one devcontainer, controls Claude Code.

## Files

- `cli.py`: `vibing devcontainer-runtime --devcontainer-id ...`.
- `claude_runner.py`: starts/streams Claude Code process.
- `command_handler.py`: maps agent-session commands and Claude output to runtime events.
- `runtime.py`: simple runtime protocol/agent shell.

## Context

- Connects to API `/runtime/agent/ws` as `devcontainer_runtime_agent`.
- Tests: `tests/devcontainer_runtime`.
