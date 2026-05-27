from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection


def _checks_by_id(body: dict) -> dict[str, dict]:
    return {c["id"]: c for c in body["checks"]}


def test_diagnostics_returns_all_required_checks(client: TestClient) -> None:
    body = client.get("/api/v1/diagnostics").json()
    ids = [c["id"] for c in body["checks"]]
    assert ids == ["backend", "sqlite", "devcontainer_cli", "docker", "podman", "claude_code"]


def test_backend_check_is_ok(client: TestClient) -> None:
    body = client.get("/api/v1/diagnostics").json()
    assert _checks_by_id(body)["backend"]["status"] == "ok"


def test_sqlite_check_is_ok_when_db_initialized(client: TestClient) -> None:
    body = client.get("/api/v1/diagnostics").json()
    sqlite_check = _checks_by_id(body)["sqlite"]
    assert sqlite_check["status"] == "ok"
    assert "schema_version" in (sqlite_check["message"] or "")


def test_sqlite_check_fails_when_schema_missing(client: TestClient) -> None:
    with get_connection() as conn:
        conn.execute("DROP TABLE app_meta")
        conn.commit()
    body = client.get("/api/v1/diagnostics").json()
    assert _checks_by_id(body)["sqlite"]["status"] == "fail"


def test_placeholder_checks_are_unknown(client: TestClient) -> None:
    body = client.get("/api/v1/diagnostics").json()
    checks = _checks_by_id(body)
    for cid in ("devcontainer_cli", "docker", "podman", "claude_code"):
        assert checks[cid]["status"] == "unknown"
