# vibing_cli

Root Typer command aggregator. Public command: `vibing`.

## Files

- `__init__.py`: creates root app, mounts subcommands; root callback exposes
  `--api-url`/`--api-prefix` (env vars `VIBING_API_URL`/`VIBING_API_V1_PREFIX`) and calls
  `http.configure()`.
- `client/`: HTTP-client commands that drive the running API (`httpx`).
  - `http.py`: `configure()`/`base_url()`, `request()`, error rendering.
  - `render.py`: rich table/object rendering + shared `--json` option.
  - `devcontainers.py`: `vibing devcontainer ...` incl. nested `session` sub-app.
  - `inbox.py`, `approvals.py`, `system.py`: read endpoints.

## Commands

- `vibing dev ...`: from `vibing_api.cli`.
- `vibing runtime host ...`: host runtime worker (`vibing_host_runtime.cli`).
- `vibing runtime devcontainer ...`: agent runtime worker (`vibing_devcontainer_runtime.cli`).
- `vibing devcontainer ...`: devcontainer CRUD + lifecycle + `session` agent commands.
- `vibing inbox ...` / `vibing approval ...` / `vibing system ...`: read endpoints.

## Context

- Client commands call the live API; base URL from env. Inside the devcontainer set
  `VIBING_API_URL=http://host.docker.internal:8080` to reach the host-published API.
- No domain logic here; client modules are thin HTTP glue.
- Tests: `tests/cli/`, plus `tests/api/test_cli.py` and runtime CLI tests.
