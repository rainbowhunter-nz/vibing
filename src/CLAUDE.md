# src

Single uv Python package. Import packages below are domains, not separate distributions.

## Rules
- Use typer and rich for python CLI tools. use logzero for logging.

## Packages

- `vibing_cli`: root `vibing` Typer command.
- `vibing_api`: FastAPI Control Plane. Drives Devcontainer lifecycle in-process. Owns harness install/auth/status via `devcontainer exec` (ADR-0019). Stores harness credentials. Devcontainer status is live/in-memory (never DB). Harness status computed via exec + cached in-memory, keyed to container-running.
- `vibing_protocol`: shared runtime-channel envelope contract (outbound-only: `register`, `delegated_runs`).
- `vibing_harness`: per-harness knowledge (install/check/auth commands, cred path/format, spawn argv/env) as behavior over an injected `Executor` protocol; consumed by `vibing_api` (host `devcontainer exec`) and `vibing_devcontainer_runtime` (local subprocess). ADR-0019.
- `vibing_devcontainer_runtime`: in-container companion. Delegation-only — hosts the MCP server for Delegated Runs; checks harness status locally for `list_harnesses`. Does not install/authenticate harnesses.

## Checks

- Build: `uv build`.
- Python: `uv run ruff check src tests`, `uv run mypy src`.
