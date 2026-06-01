from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.main import create_app


@pytest.fixture
def spa_client(tmp_path: Path, db_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    static_dir = tmp_path / "dist"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "index.html").write_text("<!doctype html><body>SPA</body>")
    (static_dir / "assets" / "app.js").write_text("// js")
    monkeypatch.setattr(settings, "static_dir", str(static_dir))
    return TestClient(create_app())


def test_root_serves_index_html(spa_client: TestClient) -> None:
    response = spa_client.get("/")
    assert response.status_code == 200
    assert "SPA" in response.text


def test_spa_route_refresh_serves_index_html(spa_client: TestClient) -> None:
    response = spa_client.get("/devcontainers")
    assert response.status_code == 200
    assert "SPA" in response.text


def test_real_asset_is_served(spa_client: TestClient) -> None:
    response = spa_client.get("/assets/app.js")
    assert response.status_code == 200
    assert "// js" in response.text


def test_missing_asset_returns_404_without_fallback(spa_client: TestClient) -> None:
    response = spa_client.get("/assets/missing.js")
    assert response.status_code == 404


def test_api_routes_take_precedence_over_static(spa_client: TestClient) -> None:
    response = spa_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_api_path_returns_json_error(spa_client: TestClient) -> None:
    response = spa_client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_ERROR"


def test_no_static_mount_when_static_dir_is_none(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "static_dir", None)
    with TestClient(create_app()) as client:
        response = client.get("/some-nonexistent-path")
    assert response.status_code == 404
    # Must be FastAPI's JSON 404, not a static file mount 404.
    assert response.headers["content-type"].startswith("application/json")
