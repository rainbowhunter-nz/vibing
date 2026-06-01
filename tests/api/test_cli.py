from pathlib import Path

from typer.testing import CliRunner

from vibing_api.core.database import get_connection, init_db
from vibing_api.dev.sample_data import (
    SAMPLE_ID_PREFIX,
    SAMPLE_DEVCONTAINERS,
    seed as seed_helper,
)
from vibing_cli import app

runner = CliRunner()


def test_root_cli_exposes_runtime_subcommands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "host-runtime" in result.output
    assert "devcontainer-runtime" in result.output


def test_seed_command_inserts_sample_rows(db_path: Path) -> None:
    result = runner.invoke(app, ["dev", "sample_data", "seed"])

    assert result.exit_code == 0, result.output
    assert "Seeded" in result.output

    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM devcontainers WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()
    assert row[0] == len(SAMPLE_DEVCONTAINERS)


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
            "SELECT COUNT(*) FROM devcontainers WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()
    assert row[0] == 0


def test_status_command_reports_counts(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        seed_helper(conn)
        conn.commit()

    result = runner.invoke(app, ["dev", "sample_data", "status"])

    assert result.exit_code == 0, result.output
    for table_name in ("devcontainers", "agent_sessions", "approval_requests", "inbox_events"):
        assert table_name in result.output
    assert str(len(SAMPLE_DEVCONTAINERS)) in result.output
