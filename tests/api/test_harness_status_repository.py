import sqlite3
from vibing_api.core.schema import apply_schema
from vibing_api.repositories.harness_status import HarnessStatusRepository


def _conn():
    c = sqlite3.connect(":memory:")
    apply_schema(c)
    c.execute(
        "INSERT INTO devcontainers (id,name,local_path,status,created_at,updated_at) "
        "VALUES ('dc1','n','/p','running','t','t')"
    )
    return c


def test_upsert_then_list():
    conn = _conn()
    repo = HarnessStatusRepository(conn)
    repo.upsert("dc1", "codex", installed=True, authenticated=False)
    repo.upsert("dc1", "codex", installed=True, authenticated=True)  # overwrite
    repo.upsert("dc1", "cursor", installed=False, authenticated=False)
    rows = {r.name: r for r in repo.list("dc1")}
    assert rows["codex"].authenticated is True
    assert rows["cursor"].installed is False
