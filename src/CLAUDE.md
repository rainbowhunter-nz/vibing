# src

Single uv Python package. Import packages below are domains, not separate distributions.

## Packages

- `vibing_cli`: root `vibing` Typer command.
- `vibing_api`: FastAPI control plane, SQLite, projections, runtime WS intake.
- `vibing_protocol`: shared command/event/envelope contract.
- `vibing_runtime_client`: shared runtime WebSocket client.
- `vibing_host_runtime`: host worker. Controls Dev Container CLI.
- `vibing_devcontainer_runtime`: agent worker. Runs inside container.

## Checks

- Build: `uv build`.
- Python: `uv run ruff check src tests`, `uv run mypy src`.
