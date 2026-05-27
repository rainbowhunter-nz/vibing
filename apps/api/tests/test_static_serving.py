from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.main import create_app


def test_static_dir_defaults_to_none() -> None:
    assert settings.static_dir is None


def test_static_files_served_when_static_dir_configured(
    tmp_path: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>vibing</h1>")
    monkeypatch.setattr(settings, "static_dir", str(static_dir))
    with TestClient(create_app()) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert b"vibing" in response.content


def test_api_routes_take_precedence_over_static(
    tmp_path: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>vibing</h1>")
    monkeypatch.setattr(settings, "static_dir", str(static_dir))
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_no_static_mount_when_static_dir_is_none(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "static_dir", None)
    with TestClient(create_app()) as client:
        response = client.get("/some-nonexistent-path")
    assert response.status_code == 404
    # Must be FastAPI's JSON 404, not a static file mount 404
    assert response.headers["content-type"].startswith("application/json")
