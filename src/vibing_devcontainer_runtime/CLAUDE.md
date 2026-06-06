# vibing_devcontainer_runtime

Agent worker. Runs inside one devcontainer, controls Claude Code.

## Files

- `cli.py`: `vibing devcontainer-runtime --devcontainer-id ...`.
- `claude_runner.py`: starts/streams Claude Code process.
- `command_handler.py`: maps agent-session commands and Claude output to runtime events.
- `transcript.py`: parses Claude's on-disk JSONL into normalized turns (ADR-0009); the
  only place pinned to Claude's file format. Missing file -> []. Projects-base injectable.
- `runtime.py`: simple runtime protocol/agent shell.

## Context

- Connects to API `/runtime/agent/ws` as `devcontainer_runtime_agent`.
- Tests: `tests/devcontainer_runtime`.
