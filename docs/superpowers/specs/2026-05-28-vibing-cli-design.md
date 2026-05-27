# Vibing CLI (Typer + Rich)

## Goal

Expose the local sample-data tooling as a Typer-based CLI, invoked as:

```
vibing dev sample_data seed
vibing dev sample_data reset
vibing dev sample_data status
```

Replace the existing `python -m vibing_api.dev.sample_data` argparse wrapper. The library helpers (`seed`, `reset`, `status` functions) stay put; only the user-facing entry point changes.

## Why

The argparse wrapper was the minimum viable command surface for VIB-13. A Typer CLI gives a proper `vibing` console script that can grow additional command groups, and Rich makes the status output readable as a table instead of bare `name: count` lines. The user-facing invocation also reads more naturally than `python -m ...`.

## File Layout

```
apps/api/
├── pyproject.toml                  # +typer, +rich (runtime deps); +[project.scripts] vibing
└── src/vibing_api/
    ├── cli/
    │   ├── __init__.py             # NEW — top-level `vibing` Typer app, registers `dev` group
    │   └── dev.py                  # NEW — `dev` group + `sample_data` group with 3 commands
    └── dev/
        └── sample_data.py          # MODIFIED — library helpers only; argparse machinery removed
```

The CLI imports library helpers from `vibing_api.dev.sample_data`. The library does no printing and has no CLI dependencies.

## Entry Point

```toml
[project.scripts]
vibing = "vibing_api.cli:app"
```

`typer.Typer` instances are callable, so the `app` object works directly as a console_script target. `uv sync` (automatic after `uv add`) installs the `vibing` script into the venv's `bin/`.

## CLI Structure

### `vibing_api/cli/__init__.py`

- Create `app = typer.Typer(name="vibing", help="Vibing local development CLI.", no_args_is_help=True)`.
- Import `dev_app` from `vibing_api.cli.dev` and register it: `app.add_typer(dev_app, name="dev")`.
- No `if __name__ == "__main__":` block. The `vibing` console script is the only entry; `python -m vibing_api.cli` is not a supported invocation.

### `vibing_api/cli/dev.py`

- Create `dev_app = typer.Typer(help="Local development helpers.", no_args_is_help=True)`.
- Create `sample_data_app = typer.Typer(help="Manage local sample data.", no_args_is_help=True)`.
- Register: `dev_app.add_typer(sample_data_app, name="sample_data")` — explicit `name=` overrides Typer's default kebab-case conversion so the invocation matches the user's requested form.
- Module-level `console = Console()`.
- Three commands (`@sample_data_app.command("seed" | "reset" | "status")`), each calling `init_db()` and the matching library helper inside `get_connection()`.

### Rich treatment

- `seed` → `console.print(f"[green]Seeded {inserted} rows.[/green]")`
- `reset` → `console.print(f"[yellow]Removed {removed} sample rows.[/yellow]")`
- `status` → `rich.table.Table` titled "Sample data" with columns `Table` (left) and `Rows` (right-justified). Iterate `sample_data.status(conn).items()` to populate rows.

No spinners, no panels.

## Library Changes (`vibing_api/dev/sample_data.py`)

Keep:
- Module docstring
- Constants: `SAMPLE_ID_PREFIX`, `SAMPLE_NAME_PREFIX`, `FIXED_TS`
- Dataset tuples: `SAMPLE_WORKSPACES`, `SAMPLE_AGENT_SESSIONS`, `SAMPLE_APPROVAL_REQUESTS`, `SAMPLE_INBOX_EVENTS`
- `_DATASET` ordering constant
- Public helpers: `seed(conn)`, `reset(conn)`, `status(conn)`

Delete:
- `_cmd_seed`, `_cmd_reset`, `_cmd_status`
- `main(argv)` and the argparse wiring
- `if __name__ == "__main__":` block
- `import argparse`, `import sys` (no longer used)
- `from vibing_api.core.database import get_connection, init_db` — the library helpers take a `conn` parameter and don't open connections themselves; only the deleted `_cmd_*` functions used these imports. They move to `cli/dev.py`.

## Test Changes

### Keep unchanged
- `test_seed_inserts_curated_dataset`
- `test_seed_is_idempotent`
- `test_reset_removes_only_sample_rows`
- `test_reset_on_empty_db_is_safe`
- `test_status_counts_sample_rows`
- `test_seeded_sample_workspaces_visible_via_api`

These exercise the library helpers, which are unmoved.

### Replace
- `test_main_dispatches_subcommands` (argparse-specific) → delete.

### Add
New file `apps/api/tests/test_cli.py` covering the three commands via `typer.testing.CliRunner`:

- `test_cli_seed_inserts_rows` — invoke `["dev", "sample_data", "seed"]` on the top-level `app`, assert exit code 0 and that workspace count goes from 0 to 3.
- `test_cli_reset_removes_rows` — seed first (via library helper), invoke `["dev", "sample_data", "reset"]`, assert exit 0 and workspaces gone.
- `test_cli_status_reports_counts` — seed, invoke `["dev", "sample_data", "status"]`, assert exit 0 and that table names appear in stdout.

Reuse the existing `db_path` fixture so the CLI hits a per-test tmp SQLite.

## README

In the "Sample data (local development only)" subsection, replace:

```
uv run python -m vibing_api.dev.sample_data seed
uv run python -m vibing_api.dev.sample_data status
uv run python -m vibing_api.dev.sample_data reset
```

with:

```
uv run vibing dev sample_data seed
uv run vibing dev sample_data status
uv run vibing dev sample_data reset
```

Marker convention note (`sample-` prefix) stays as-is.

## Dependencies

Add via `uv add` (NOT manual pyproject.toml edits, per project CLAUDE.md):

- `typer`
- `rich`

Both as main project dependencies (not dev-group), because the `vibing` console script needs them at runtime even in installed-dev mode.

## Acceptance Criteria

1. `uv run vibing dev sample_data seed` prints a green confirmation line and inserts the 12-row curated dataset.
2. `uv run vibing dev sample_data reset` prints a yellow confirmation line and removes every `sample-` row.
3. `uv run vibing dev sample_data status` prints a Rich table with one row per seeded table and the current count.
4. `uv run vibing` with no args prints help and exits non-zero (Typer default with `no_args_is_help=True`).
5. `uv run vibing dev` and `uv run vibing dev sample_data` likewise show their subgroup help.
6. The argparse entry (`python -m vibing_api.dev.sample_data`) no longer exists.
7. All existing library tests still pass. New CLI tests pass. `ruff check` clean, `mypy` clean.

## Out of Scope

- Other `vibing` subcommands (no `serve`, `migrate`, `workspaces`, etc.) — only what the requested invocation needs.
- Global flags (`--verbose`, `--db-path`, `--json`).
- Tab completion / shell-completion install command.
- Backwards-compat shim for the old `python -m vibing_api.dev.sample_data` invocation — the previous design decision was to replace, not keep both.

## Risks

- **Console-script target as a `Typer` instance.** Typer instances are callable; this is the standard pattern (`typer.Typer().__call__` invokes the CLI). Verified by Typer's own docs but worth a smoke test post-install.
- **`uv add` modifying `pyproject.toml`.** Project rule says "avoid modifying `pyproject.toml` — use `uv` instead." `uv add` is the sanctioned tool for this; the rule prohibits *manual* edits, not `uv add`. Confirmed acceptable.
- **Settings cache during CLI test runs.** The `db_path` fixture monkeypatches the settings instance before the CLI command imports `get_connection`. If a CLI test imports `vibing_api.cli` at module top-level before the fixture runs, `settings.database_path` could be locked in. Mitigation: lazy imports inside the test functions, or rely on `get_connection` reading settings at call time (it does — verified in the existing argparse `_cmd_*` flow which works the same way).
