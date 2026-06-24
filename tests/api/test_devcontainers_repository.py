from pathlib import Path
import pytest
from vibing_api.core.database import get_connection, init_db
from vibing_api.repositories.devcontainers import DevcontainerRepository


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vibing_api.core.config import settings
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    init_db()


def test_upsert_inserts_then_is_idempotent_and_keeps_name() -> None:
    with get_connection() as conn:
        repo = DevcontainerRepository(conn)
        first = repo.upsert("My App", "/tmp/app")
        conn.commit()
        again = repo.upsert("Renamed", "/tmp/app")  # different name ignored
        conn.commit()
        rows = repo.list()
    assert again.id == first.id
    assert again.name == "My App"
    assert len([r for r in rows if r.local_path == "/tmp/app"]) == 1
