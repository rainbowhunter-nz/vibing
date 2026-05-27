# Vibing CLI (Typer + Rich) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `python -m vibing_api.dev.sample_data` argparse wrapper with a Typer + Rich CLI invoked as `vibing dev sample_data {seed,reset,status}`.

**Architecture:** A small `vibing_api.cli` package holds a top-level `Typer()` `app`, a `dev` sub-app, and a `sample_data` sub-app with three commands. The CLI imports the existing library helpers from `vibing_api.dev.sample_data` (which stays pure — no printing, no CLI deps). A `[project.scripts]` entry exposes `vibing` as a console script.

**Tech Stack:** Python 3.13, Typer, Rich, pytest (with `typer.testing.CliRunner`), uv.

**Spec:** `docs/superpowers/specs/2026-05-28-vibing-cli-design.md`

**Working directory for all commands:** `/workspaces/vibing/apps/api/`

---

### Task 1: Add typer + rich dependencies

**Files:**
- Modify: `apps/api/pyproject.toml` (via `uv add`)
- Modify: `apps/api/uv.lock` (via `uv add`)

- [ ] **Step 1: Add the two runtime deps**

From `apps/api/`:
```bash
uv add typer rich
```

Per project rule, never edit `pyproject.toml` manually for dep changes — `uv add` is the sanctioned tool. It will append both packages to the `dependencies` array and update `uv.lock`.

- [ ] **Step 2: Smoke-import both packages**

```bash
uv run python -c "import typer, rich; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/api/pyproject.toml apps/api/uv.lock
git commit -m "$(cat <<'EOF'
Add typer and rich for the vibing CLI

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Register the `vibing` console script and stub the cli package

**Files:**
- Modify: `apps/api/pyproject.toml` (manual edit — `uv` has no command for script entries)
- Create: `apps/api/src/vibing_api/cli/__init__.py`
- Create: `apps/api/src/vibing_api/cli/dev.py`

- [ ] **Step 1: Add the console-script entry to `pyproject.toml`**

Insert this block after the `[dependency-groups]` section and before `[build-system]`:

```toml
[project.scripts]
vibing = "vibing_api.cli:app"
```

The project rule against manual `pyproject.toml` edits is about dep management (handled by `uv add`). `[project.scripts]` is configuration `uv` doesn't expose a command for, so a one-time manual edit is the only path.

- [ ] **Step 2: Create empty cli package files**

Create `apps/api/src/vibing_api/cli/__init__.py` with a placeholder so the import target resolves:

```python
import typer

app = typer.Typer(name="vibing", help="Vibing local development CLI.", no_args_is_help=True)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
```

The callback exists only so `uv run vibing --help` works while there are no subcommands yet — without it, Typer raises `RuntimeError: Could not get a command for this Typer instance`. Task 4 removes the callback once `dev_app` is registered (at that point `no_args_is_help=True` handles the no-subcommand case natively).

Create `apps/api/src/vibing_api/cli/dev.py` with a minimal stub (Task 4 fills in the rest):

```python
import typer

dev_app = typer.Typer(help="Local development helpers.", no_args_is_help=True)
```

- [ ] **Step 3: Re-sync so the `vibing` script lands in the venv**

```bash
uv sync
```

- [ ] **Step 4: Smoke-test the script is registered**

```bash
uv run vibing --help
```
Expected: Typer prints the top-level help (no `dev` group yet — we'll add it in Task 4). Exit code 0 if `--help`, 2 otherwise.

- [ ] **Step 5: Commit**

```bash
git add apps/api/pyproject.toml apps/api/src/vibing_api/cli/__init__.py apps/api/src/vibing_api/cli/dev.py
git commit -m "$(cat <<'EOF'
Register vibing console script and stub cli package

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Write a failing test for the `seed` CLI command

**Files:**
- Create: `apps/api/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_cli.py`:

```python
from pathlib import Path

from typer.testing import CliRunner

from vibing_api.cli import app
from vibing_api.core.database import get_connection, init_db
from vibing_api.dev.sample_data import SAMPLE_ID_PREFIX, SAMPLE_WORKSPACES

runner = CliRunner()


def test_seed_command_inserts_sample_rows(db_path: Path) -> None:
    result = runner.invoke(app, ["dev", "sample_data", "seed"])

    assert result.exit_code == 0, result.output
    assert "Seeded" in result.output

    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM workspaces WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()
    assert row[0] == len(SAMPLE_WORKSPACES)
```

The `db_path` fixture already lives in `tests/conftest.py` and monkeypatches `settings.database_url` to a per-test tmp SQLite.

- [ ] **Step 2: Run the test — expect failure**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: FAIL — `dev` is not a recognized command (the cli stub has no `dev` group). Error output will look like `Error: No such command 'dev'.` and the exit code will be 2, not 0.

(No commit yet — failing test alone doesn't get committed; we commit after the green bar in Task 4.)

---

### Task 4: Build the dev group + sample_data group + seed command

**Files:**
- Modify: `apps/api/src/vibing_api/cli/__init__.py`
- Modify: `apps/api/src/vibing_api/cli/dev.py`

- [ ] **Step 1: Implement `cli/dev.py`**

Replace the empty `apps/api/src/vibing_api/cli/dev.py` with:

```python
import typer
from rich.console import Console

from vibing_api.core.database import get_connection, init_db
from vibing_api.dev import sample_data as sd

dev_app = typer.Typer(help="Local development helpers.", no_args_is_help=True)
sample_data_app = typer.Typer(help="Manage local sample data.", no_args_is_help=True)
dev_app.add_typer(sample_data_app, name="sample_data")

console = Console()


@sample_data_app.command("seed")
def seed() -> None:
    """Insert the curated sample dataset."""
    init_db()
    with get_connection() as conn:
        inserted = sd.seed(conn)
        conn.commit()
    console.print(f"[green]Seeded {inserted} rows.[/green]")
```

The explicit `name="sample_data"` on `add_typer` overrides Typer's default kebab-case conversion so the invocation matches the requested form.

- [ ] **Step 2: Wire `dev_app` into the top-level `app` and remove the Task 2 callback**

Replace `apps/api/src/vibing_api/cli/__init__.py` with:

```python
import typer

from vibing_api.cli.dev import dev_app

app = typer.Typer(name="vibing", help="Vibing local development CLI.", no_args_is_help=True)
app.add_typer(dev_app, name="dev")
```

The Task 2 `main(ctx)` callback (added to make `--help` work before any subcommands existed) is no longer needed — with `dev_app` registered, `no_args_is_help=True` handles the no-subcommand case natively. Delete the callback as part of this step.

- [ ] **Step 3: Run the failing test — expect PASS**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: `test_seed_command_inserts_sample_rows PASSED`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/vibing_api/cli/__init__.py apps/api/src/vibing_api/cli/dev.py apps/api/tests/test_cli.py
git commit -m "$(cat <<'EOF'
Wire vibing dev sample_data seed via Typer

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Add the `reset` command (TDD)

**Files:**
- Modify: `apps/api/tests/test_cli.py`
- Modify: `apps/api/src/vibing_api/cli/dev.py`

- [ ] **Step 1: Add the failing test**

Update the import block in `apps/api/tests/test_cli.py` to also pull in the library `seed` helper (aliased to avoid clashing with the test function names):

```python
from vibing_api.dev.sample_data import (
    SAMPLE_ID_PREFIX,
    SAMPLE_WORKSPACES,
    seed as seed_helper,
)
```

Then append:

```python
def test_reset_command_removes_sample_rows(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        seed_helper(conn)
        conn.commit()

    result = runner.invoke(app, ["dev", "sample_data", "reset"])

    assert result.exit_code == 0, result.output
    assert "Removed" in result.output

    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM workspaces WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()
    assert row[0] == 0
```

- [ ] **Step 2: Run it — expect failure**

```bash
uv run pytest tests/test_cli.py::test_reset_command_removes_sample_rows -v
```
Expected: FAIL — `No such command 'reset'`. Exit code non-zero.

- [ ] **Step 3: Implement the `reset` command**

Append to `apps/api/src/vibing_api/cli/dev.py`:

```python
@sample_data_app.command("reset")
def reset() -> None:
    """Remove all sample-prefixed rows."""
    init_db()
    with get_connection() as conn:
        removed = sd.reset(conn)
        conn.commit()
    console.print(f"[yellow]Removed {removed} sample rows.[/yellow]")
```

- [ ] **Step 4: Run the test — expect PASS**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: both CLI tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/vibing_api/cli/dev.py apps/api/tests/test_cli.py
git commit -m "$(cat <<'EOF'
Add vibing dev sample_data reset command

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add the `status` command (TDD)

**Files:**
- Modify: `apps/api/tests/test_cli.py`
- Modify: `apps/api/src/vibing_api/cli/dev.py`

- [ ] **Step 1: Add the failing test**

Append to `apps/api/tests/test_cli.py`:

```python
def test_status_command_reports_counts(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        seed_helper(conn)
        conn.commit()

    result = runner.invoke(app, ["dev", "sample_data", "status"])

    assert result.exit_code == 0, result.output
    for table_name in ("workspaces", "agent_sessions", "approval_requests", "inbox_events"):
        assert table_name in result.output
    assert str(len(SAMPLE_WORKSPACES)) in result.output
```

- [ ] **Step 2: Run it — expect failure**

```bash
uv run pytest tests/test_cli.py::test_status_command_reports_counts -v
```
Expected: FAIL — `No such command 'status'`.

- [ ] **Step 3: Implement the `status` command**

First, add `from rich.table import Table` to the top-of-file imports in `apps/api/src/vibing_api/cli/dev.py`. The import block should read:

```python
import typer
from rich.console import Console
from rich.table import Table

from vibing_api.core.database import get_connection, init_db
from vibing_api.dev import sample_data as sd
```

Then append the command to the bottom of the file:

```python
@sample_data_app.command("status")
def status() -> None:
    """Print per-table sample row counts."""
    init_db()
    with get_connection() as conn:
        counts = sd.status(conn)
    table = Table(title="Sample data")
    table.add_column("Table")
    table.add_column("Rows", justify="right")
    for name, count in counts.items():
        table.add_row(name, str(count))
    console.print(table)
```

- [ ] **Step 4: Run all CLI tests — expect PASS**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: 3 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/vibing_api/cli/dev.py apps/api/tests/test_cli.py
git commit -m "$(cat <<'EOF'
Add vibing dev sample_data status command with Rich table

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: End-to-end smoke test the `vibing` console script

**Files:** (none — verification only)

- [ ] **Step 1: Help output at each level**

```bash
uv run vibing --help
uv run vibing dev --help
uv run vibing dev sample_data --help
```
Expected: Each prints help. The third lists `seed`, `reset`, `status` as commands. All exit 0.

- [ ] **Step 2: Run against a fresh tmp DB**

```bash
VIBING_DATABASE_URL="sqlite:///$(mktemp -d)/cli-smoke.db" uv run vibing dev sample_data status
```
Expected: A Rich table titled "Sample data" with four rows, each showing `0`. (`VIBING_DATABASE_URL` is the env-var form of `settings.database_url` — `env_prefix="VIBING_"` + field name, per `apps/api/src/vibing_api/core/config.py`.)

- [ ] **Step 3: Seed, status, reset, status loop**

```bash
DB=$(mktemp -d)/cli-smoke.db
VIBING_DATABASE_URL="sqlite:///$DB" uv run vibing dev sample_data seed
VIBING_DATABASE_URL="sqlite:///$DB" uv run vibing dev sample_data status
VIBING_DATABASE_URL="sqlite:///$DB" uv run vibing dev sample_data reset
VIBING_DATABASE_URL="sqlite:///$DB" uv run vibing dev sample_data status
```
Expected: Seed prints "Seeded 12 rows." in green. First status shows 3/3/2/4 rows. Reset prints "Removed 12 sample rows." in yellow. Second status shows all zeros.

(No commit — verification only.)

---

### Task 8: Delete the argparse machinery from the library

**Files:**
- Modify: `apps/api/src/vibing_api/dev/sample_data.py`
- Modify: `apps/api/tests/test_sample_data.py`

- [ ] **Step 1: Remove dead code from `sample_data.py`**

In `apps/api/src/vibing_api/dev/sample_data.py`, delete these blocks entirely:

- `import argparse`
- `import sys`
- `from vibing_api.core.database import get_connection, init_db` (the library helpers don't open connections — only `_cmd_*` used these)
- The three `_cmd_seed`, `_cmd_reset`, `_cmd_status` functions
- The `main(argv)` function
- The `if __name__ == "__main__":` block at end of file

Keep everything else (module docstring, constants, dataset tuples, `_DATASET`, and the three public helpers `seed`, `reset`, `status`).

- [ ] **Step 2: Remove the now-broken imports and test from `test_sample_data.py`**

In `apps/api/tests/test_sample_data.py`:

- Remove `main` from the `from vibing_api.dev.sample_data import (...)` block.
- Delete the entire `test_main_dispatches_subcommands` function (it tests argparse machinery that no longer exists).

- [ ] **Step 3: Run the full API test suite — expect PASS**

```bash
uv run pytest -v
```
Expected: All tests pass. The library `seed/reset/status` tests still cover behaviour; CLI tests from Tasks 4–6 cover the new entry surface.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/vibing_api/dev/sample_data.py apps/api/tests/test_sample_data.py
git commit -m "$(cat <<'EOF'
Remove argparse wrapper from sample_data library

The Typer CLI is now the only entry point.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Update the README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the three command lines in the "Sample data (local development only)" subsection**

In `README.md`, the subsection currently contains:

```
uv run python -m vibing_api.dev.sample_data seed
uv run python -m vibing_api.dev.sample_data status
uv run python -m vibing_api.dev.sample_data reset
```

Replace with:

```
uv run vibing dev sample_data seed
uv run vibing dev sample_data status
uv run vibing dev sample_data reset
```

Leave the surrounding prose (including the `sample-` marker-convention note) unchanged.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
Update README to use vibing CLI for sample data

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Final verification — lint, type-check, full test suite

**Files:** (none — verification only)

- [ ] **Step 1: Ruff over the files this branch touched**

From `apps/api/`:
```bash
uv run ruff check src/vibing_api/cli/ src/vibing_api/dev/sample_data.py tests/test_cli.py tests/test_sample_data.py
```
Expected: `All checks passed!`

The repo has pre-existing ruff errors in `tests/test_runtime_events.py` (last touched in commit `e3e3ae6`, unrelated to this work). Scoping the check to files this branch touched keeps the lint signal meaningful without bundling in an unrelated cleanup.

- [ ] **Step 2: Mypy over the same scope**

```bash
uv run mypy src/vibing_api/cli/ src/vibing_api/dev/sample_data.py tests/test_cli.py tests/test_sample_data.py
```
Expected: `Success: no issues found in N source files`

- [ ] **Step 3: Full pytest**

```bash
uv run pytest -v
```
Expected: All tests pass (the 80 pre-existing tests minus the deleted `test_main_dispatches_subcommands`, plus the 3 new CLI tests).

No commit — verification only.

---

## Notes for the implementer

- **The `db_path` fixture** in `apps/api/tests/conftest.py` already monkeypatches `settings.database_url` to a per-test tmp file. Every test in `test_cli.py` should take `db_path` as a parameter to get DB isolation, even though only the side-effect verifications reach into the DB directly.
- **Rich output in tests.** `CliRunner` captures stdout. Rich's `Console` detects the non-TTY and emits plain ASCII; ANSI codes do not appear in `result.output`. The assertions on substring presence ("Seeded", table names, etc.) are stable.
- **Order of operations matters in Task 6** — the `Table` import must be at the top of `dev.py`, not inline in the function, to keep imports tidy and survive `ruff check`.
- **Don't touch `.devcontainer/post_create_setup.sh`** — there is an unrelated uncommitted modification to that file from the user's IDE session. It's outside this plan's scope.
