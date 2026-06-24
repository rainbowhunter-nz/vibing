from pathlib import Path
import pytest
from vibing_api.core.database import get_connection, init_db
from vibing_api.core.devcontainer_sync import sync_devcontainers
from vibing_api.core.live_state import LiveStateStore
from vibing_api.repositories.devcontainers import DevcontainerRepository


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vibing_api.core.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    init_db()


def _mk(root: Path, name: str) -> Path:
    d = root / name
    (d / ".devcontainer").mkdir(parents=True)
    return d


def test_sync_adds_new_evicts_missing(tmp_path: Path) -> None:
    root = tmp_path / "dcs"
    keep = _mk(root, "keep")
    live = LiveStateStore()

    sync_devcontainers(str(root), live)  # first sync: adds "keep"
    with get_connection() as conn:
        paths = {r.local_path for r in DevcontainerRepository(conn).list()}
    assert str(keep) in paths

    # Pre-seed live-state for a soon-to-be-stale manual row, then remove its folder
    gone = _mk(root, "gone")
    sync_devcontainers(str(root), live)
    with get_connection() as conn:
        gone_id = next(
            r.id for r in DevcontainerRepository(conn).list() if r.local_path == str(gone)
        )
    live.set_harness(gone_id, [])
    import shutil

    shutil.rmtree(gone)

    sync_devcontainers(str(root), live)  # evicts "gone"
    with get_connection() as conn:
        paths = {r.local_path for r in DevcontainerRepository(conn).list()}
    assert str(gone) not in paths
    assert str(keep) in paths
    assert live.get_harness(gone_id) is None
