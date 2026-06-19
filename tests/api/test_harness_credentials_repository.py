import sqlite3

from vibing_api.core.schema import apply_schema
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    apply_schema(c)
    return c


def test_get_returns_none_when_absent():
    repo = HarnessCredentialRepository(_conn())
    assert repo.get("codex") is None


def test_upsert_then_get_roundtrips_blob():
    conn = _conn()
    repo = HarnessCredentialRepository(conn)
    blob = {"api_key": "sk-test", "org": "acme"}
    repo.upsert("codex", blob)
    conn.commit()
    assert repo.get("codex") == blob


def test_upsert_overwrites_existing():
    conn = _conn()
    repo = HarnessCredentialRepository(conn)
    repo.upsert("codex", {"v": 1})
    repo.upsert("codex", {"v": 2})
    conn.commit()
    assert repo.get("codex") == {"v": 2}


def test_list_returns_all_names():
    conn = _conn()
    repo = HarnessCredentialRepository(conn)
    repo.upsert("cursor", {"x": 1})
    repo.upsert("codex", {"x": 2})
    conn.commit()
    assert repo.list() == ["codex", "cursor"]  # alphabetical


def test_list_empty_when_no_credentials():
    repo = HarnessCredentialRepository(_conn())
    assert repo.list() == []
