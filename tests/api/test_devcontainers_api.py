from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.main import create_app


def test_create_devcontainer_returns_metadata(client: TestClient) -> None:
    response = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": "/tmp/demo"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "demo"
    assert body["local_path"] == "/tmp/demo"
    assert body["status"] == "stopped"
    assert body["id"]
    assert body["created_at"]
    assert body["updated_at"]


def test_create_devcontainer_returns_local_path(client: TestClient) -> None:
    response = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": "/tmp/demo"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["local_path"] == "/tmp/demo"
    assert "source_value" not in body


def test_create_devcontainer_rejects_missing_name(client: TestClient) -> None:
    response = client.post("/api/v1/devcontainers", json={"local_path": "/tmp/demo"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_create_devcontainer_rejects_missing_local_path(client: TestClient) -> None:
    response = client.post("/api/v1/devcontainers", json={"name": "demo"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_create_devcontainer_rejects_empty_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/devcontainers",
        json={"name": "", "local_path": "/tmp/demo"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_devcontainer_rejects_empty_local_path(client: TestClient) -> None:
    response = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": ""},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_devcontainers_returns_created_devcontainers(client: TestClient) -> None:
    client.post("/api/v1/devcontainers", json={"name": "a", "local_path": "/tmp/a"})
    client.post("/api/v1/devcontainers", json={"name": "b", "local_path": "/tmp/b"})

    response = client.get("/api/v1/devcontainers")
    assert response.status_code == 200
    body = response.json()
    names = sorted(item["name"] for item in body["items"])
    assert names == ["a", "b"]
    for item in body["items"]:
        assert "source_type" not in item
        assert "source_value" not in item


def test_list_devcontainers_empty(client: TestClient) -> None:
    response = client.get("/api/v1/devcontainers")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_get_devcontainer_by_id(client: TestClient) -> None:
    create = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": "/tmp/demo"},
    ).json()

    response = client.get(f"/api/v1/devcontainers/{create['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == create["id"]
    assert body["name"] == "demo"
    assert body["local_path"] == "/tmp/demo"
    assert body["status"] == "stopped"


def test_get_devcontainer_unknown_id_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/devcontainers/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "DEVCONTAINER_NOT_FOUND"
    assert "does-not-exist" in body["error"]["message"]


def test_update_devcontainer_name(client: TestClient) -> None:
    created = client.post(
        "/api/v1/devcontainers",
        json={"name": "old", "local_path": "/tmp/demo"},
    ).json()

    response = client.patch(
        f"/api/v1/devcontainers/{created['id']}",
        json={"name": "new"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["name"] == "new"
    assert body["status"] == created["status"]
    assert body["local_path"] == created["local_path"]
    assert body["updated_at"] >= created["updated_at"]


def test_update_devcontainer_name_persists_changes(client: TestClient) -> None:
    created = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": "/tmp/demo"},
    ).json()
    client.patch(
        f"/api/v1/devcontainers/{created['id']}",
        json={"name": "renamed"},
    )

    response = client.get(f"/api/v1/devcontainers/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "renamed"


def test_update_devcontainer_rejects_empty_name(client: TestClient) -> None:
    created = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": "/tmp/demo"},
    ).json()

    response = client.patch(
        f"/api/v1/devcontainers/{created['id']}",
        json={"name": ""},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_update_devcontainer_ignores_read_only_fields(client: TestClient) -> None:
    created = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": "/tmp/demo"},
    ).json()

    response = client.patch(
        f"/api/v1/devcontainers/{created['id']}",
        json={"id": "hijacked", "local_path": "/etc/passwd", "created_at": "1970-01-01T00:00:00Z"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["local_path"] == created["local_path"]
    assert body["created_at"] == created["created_at"]


def test_update_devcontainer_unknown_id_returns_not_found(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/devcontainers/does-not-exist",
        json={"name": "x"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"


def test_delete_devcontainer_returns_no_content(client: TestClient) -> None:
    created = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": "/tmp/demo"},
    ).json()

    response = client.delete(f"/api/v1/devcontainers/{created['id']}")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_devcontainer_removes_from_get_and_list(client: TestClient) -> None:
    created = client.post(
        "/api/v1/devcontainers",
        json={"name": "demo", "local_path": "/tmp/demo"},
    ).json()
    client.delete(f"/api/v1/devcontainers/{created['id']}")

    get_response = client.get(f"/api/v1/devcontainers/{created['id']}")
    assert get_response.status_code == 404

    list_response = client.get("/api/v1/devcontainers")
    assert list_response.status_code == 200
    assert list_response.json() == {"items": []}


def test_delete_devcontainer_unknown_id_returns_not_found(client: TestClient) -> None:
    response = client.delete("/api/v1/devcontainers/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"


def test_create_then_list_shows_status(client: TestClient) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "demo", "local_path": "/tmp/demo"}
    ).json()
    assert created["status"] == "stopped"  # no container running

    listed = client.get("/api/v1/devcontainers").json()["items"]
    row = next(r for r in listed if r["id"] == created["id"])
    assert row["status"] == "stopped"


def test_view_has_no_source_field(client: TestClient, fake_cli) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "n", "local_path": "/tmp/ns"}
    ).json()
    assert "source" not in created
    got = client.get(f"/api/v1/devcontainers/{created['id']}").json()
    assert "source" not in got


def test_get_unknown_id_404(client: TestClient) -> None:
    resp = client.get("/api/v1/devcontainers/nope")
    assert resp.status_code == 404


def test_status_running_when_docker_reports_folder(client: TestClient, fake_cli) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "r", "local_path": "/tmp/r"}
    ).json()
    fake_cli.running = {"/tmp/r"}
    row = next(
        r for r in client.get("/api/v1/devcontainers").json()["items"] if r["id"] == created["id"]
    )
    assert row["status"] == "running"


def test_delete_manual_removes_container_and_record(client: TestClient, fake_cli) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "d", "local_path": "/tmp/d"}
    ).json()
    resp = client.delete(f"/api/v1/devcontainers/{created['id']}")
    assert resp.status_code == 204
    assert "/tmp/d" in fake_cli.removed
    assert client.get(f"/api/v1/devcontainers/{created['id']}").status_code == 404


def test_delete_unknown_404(client: TestClient, fake_cli) -> None:
    assert client.delete("/api/v1/devcontainers/nope").status_code == 404


def test_remove_container_kills_but_keeps_record(client: TestClient, fake_cli) -> None:
    created = client.post(
        "/api/v1/devcontainers", json={"name": "rc", "local_path": "/tmp/rc"}
    ).json()
    resp = client.post(f"/api/v1/devcontainers/{created['id']}/remove-container")
    assert resp.status_code == 204
    assert "/tmp/rc" in fake_cli.removed
    # Entry survives: still resolvable, status back to stopped.
    got = client.get(f"/api/v1/devcontainers/{created['id']}")
    assert got.status_code == 200
    assert got.json()["status"] == "stopped"


def test_remove_container_unknown_404(client: TestClient, fake_cli) -> None:
    assert client.post("/api/v1/devcontainers/nope/remove-container").status_code == 404


def test_old_workspaces_path_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/workspaces").status_code == 404
    assert client.post("/api/v1/workspaces", json={}).status_code == 404
    assert client.get("/api/v1/workspaces/any-id").status_code == 404
    assert client.patch("/api/v1/workspaces/any-id", json={}).status_code == 404
    assert client.delete("/api/v1/workspaces/any-id").status_code == 404


@pytest.fixture
def fresh_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "vibing-restart.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{path}")
    return path


def test_devcontainers_persist_across_app_restarts(tmp_path: Path, fresh_db_path: Path) -> None:
    demo = tmp_path / "demo"
    (demo / ".devcontainer").mkdir(parents=True)

    with TestClient(create_app()) as first:
        created = first.post(
            "/api/v1/devcontainers",
            json={"name": "demo", "local_path": str(demo)},
        ).json()

    with TestClient(create_app()) as second:
        list_response = second.get("/api/v1/devcontainers")
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == created["id"]
        assert items[0]["name"] == "demo"


def test_remove_container_evicts_delegated_runs(client: TestClient, fake_cli) -> None:
    from vibing_protocol import DelegatedRunItem

    created = client.post(
        "/api/v1/devcontainers", json={"name": "rc", "local_path": "/tmp/rc2"}
    ).json()
    client.app.state.live_state.set_delegated_runs(
        created["id"],
        [
            DelegatedRunItem(
                run_id="r1",
                harness="codex",
                model="m",
                title="seed task",
                status="running",
                started_at="2026-06-20T00:00:00+00:00",
            )
        ],
    )
    client.post(f"/api/v1/devcontainers/{created['id']}/remove-container")
    assert client.app.state.live_state.get_delegated_runs(created["id"]) is None
