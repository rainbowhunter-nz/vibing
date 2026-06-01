# vibing_cli

Root Typer command aggregator. Public command: `vibing`.

## Files

- `__init__.py`: creates root app and mounts subcommands.

## Commands

- `vibing dev ...`: from `vibing_api.cli`.
- `vibing host-runtime ...`: from `vibing_host_runtime.cli`.
- `vibing devcontainer-runtime ...`: from `vibing_devcontainer_runtime.cli`.

## Context

- No domain logic here.
- Tests: `tests/api/test_cli.py` plus runtime CLI tests.
