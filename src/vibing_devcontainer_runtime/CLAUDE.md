# vibing_devcontainer_runtime

Agent worker. Runs inside one devcontainer, controls Claude Code.

## Files

- `cli.py`: `vibing devcontainer-runtime --devcontainer-id ...`.
- `claude_runner.py`: runs Claude as `--output-format stream-json` (ADR-0010), reads stdout
  line-by-line, invokes an on_delta callback per turn-delta; terminal `result` event maps to
  success/failure. Injectable `StreamRunner` seam yields a sequence of stream-json lines.
- `stream_normalizer.py`: pure Claude stream-json -> normalized turn-deltas (ADR-0010, TEXT
  only). The only NEW place pinned to Claude's wire format (mirrors transcript.py).
- `command_handler.py`: maps agent-session commands + Claude output to runtime events; live
  turn-deltas flow out via `emit_delta` (sibling to `emit`).
- `transcript.py`: parses Claude's on-disk JSONL into normalized turns (ADR-0009); the
  only place pinned to Claude's file format. Adds turn `id` from the per-message uuid
  (ADR-0010). Missing file -> []. Projects-base injectable.
- `runtime.py`: simple runtime protocol/agent shell.

## Context

- Connects to API `/runtime/agent/ws` as `devcontainer_runtime_agent`.
- Tests: `tests/devcontainer_runtime`.
