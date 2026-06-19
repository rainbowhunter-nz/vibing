# src

Single uv Python package. Import packages below are domains, not separate distributions.

## Rules
- Use typer and rich for python CLI tools. use logzero for logging.

## Packages

- `vibing_cli`: root `vibing` Typer command.
- `vibing_api`: FastAPI Control Plane. Drives Devcontainer lifecycle in-process. Stores harness credentials. Mutates read-model directly.
- `vibing_protocol`: shared command/envelope/harness-status contract.
- `vibing_devcontainer_runtime`: in-container companion. Manages harness install/auth, reports Harness Status, hosts MCP delegation server.

## Checks

- Build: `uv build`.
- Python: `uv run ruff check src tests`, `uv run mypy src`.
