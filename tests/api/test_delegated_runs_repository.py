"""Unit tests for DelegatedRunRepository."""

from pathlib import Path

import pytest

from vibing_api.core.database import get_connection, init_db
from vibing_api.repositories.delegated_runs import DelegatedRunRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_protocol import DelegatedRunItem


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vibing_api.core.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    init_db()


def _seed_devcontainer() -> str:
    with get_connection() as conn:
        dc = DevcontainerRepository(conn).create(name="test", local_path="/tmp/test")
        conn.commit()
    return dc.id


def _item(run_id: str, status: str = "running") -> DelegatedRunItem:
    return DelegatedRunItem(
        run_id=run_id,
        harness="codex",
        model="m",
        status=status,
        started_at="2026-06-20T00:00:00+00:00",
    )


def test_replace_allows_unpersisted_devcontainer() -> None:
    """Discovered devcontainers are virtual (never persisted); their runs must still store."""
    with get_connection() as conn:
        repo = DelegatedRunRepository(conn)
        repo.replace("discovered-uuid5", [_item("run-1")])
        conn.commit()
        assert {r.run_id for r in repo.list("discovered-uuid5")} == {"run-1"}


def test_replace_is_a_full_snapshot() -> None:
    dc_id = _seed_devcontainer()
    with get_connection() as conn:
        repo = DelegatedRunRepository(conn)
        repo.replace(dc_id, [_item("run-1"), _item("run-2")])
        conn.commit()
        assert {r.run_id for r in repo.list(dc_id)} == {"run-1", "run-2"}
        repo.replace(dc_id, [_item("run-3", status="completed")])
        conn.commit()
        rows = repo.list(dc_id)
    assert [r.run_id for r in rows] == ["run-3"]
    assert rows[0].status == "completed"
