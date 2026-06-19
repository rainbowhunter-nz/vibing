# vibing_devcontainer_runtime

Agent worker. Runs inside one devcontainer, controls Claude Code.

## Files

- `cli.py`: `vibing devcontainer-runtime --devcontainer-id ...`.
- `claude_runner.py`: runs Claude as `--output-format stream-json` (ADR-0010), reads stdout
  line-by-line, invokes an on_delta callback per turn-delta; terminal `result` event maps to
  success/failure. One seam: `ClaudeProcess`. The runner builds the command and a
  `ProcessFactory` turns it into a process (real subprocess in prod; a fake in tests).
- `content_blocks.py`: the one place pinned to Claude's content-block shape (`text`/`tool_use`),
  decoding it into intermediate items + the tool-input summary. `transcript.py` and
  `stream_normalizer.py` each project these items onto their own envelope, so durable transcript
  and live stream tool cards cannot drift.
- `stream_normalizer.py`: pure Claude stream-json -> normalized turn-deltas (ADR-0010). Owns the
  stream-json envelope shapes (message_start / deltas / result); content blocks go through
  `content_blocks`.
- `command_handler.py`: maps agent-session commands + Claude output to runtime events; both
  RuntimeEventEnvelopes and live TurnDeltaEnvelopes go out over the single `send`. Delegates
  in-flight run tracking to `running_sessions`.
- `running_sessions.py`: tracks the (process, task) per active session id; owns the
  stop ordering (cancel task, then terminate process) and the stop-vs-completion race.
- `transcript.py`: parses Claude's on-disk JSONL into normalized turns (ADR-0009); owns the
  file-level shapes (roles, turn `id` from the per-message uuid per ADR-0010), content blocks via
  `content_blocks`. Missing file -> []. Projects-base injectable. `respond` answers
  `transcript_request` messages; cli registers it via `client.on_request`.

## Context

- Connects to API `/runtime/agent/ws` as `devcontainer_runtime_agent`.
- Tests: `tests/devcontainer_runtime`.
