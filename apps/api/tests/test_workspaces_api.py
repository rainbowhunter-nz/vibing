from fastapi.testclient import TestClient


def test_create_workspace_returns_metadata(client: TestClient) -> None:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "demo", "local_path": "/tmp/demo"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "demo"
    assert body["local_path"] == "/tmp/demo"
    assert body["status"] == "created"
    assert body["id"]
    assert body["created_at"]
    assert body["updated_at"]


def test_create_workspace_does_not_expose_internal_source_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "demo", "local_path": "/tmp/demo"},
    )
    assert response.status_code == 201
    body = response.json()
    assert "source_type" not in body
    assert "source_path" not in body
    assert "source_value" not in body
    assert "git_url" not in body


def test_create_workspace_rejects_missing_name(client: TestClient) -> None:
    response = client.post("/api/v1/workspaces", json={"local_path": "/tmp/demo"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_create_workspace_rejects_missing_local_path(client: TestClient) -> None:
    response = client.post("/api/v1/workspaces", json={"name": "demo"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_create_workspace_rejects_empty_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "", "local_path": "/tmp/demo"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_workspace_rejects_empty_local_path(client: TestClient) -> None:
    response = client.post(
        "/api/v1/workspaces",
        json={"name": "demo", "local_path": ""},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_workspaces_returns_created_workspaces(client: TestClient) -> None:
    client.post("/api/v1/workspaces", json={"name": "a", "local_path": "/tmp/a"})
    client.post("/api/v1/workspaces", json={"name": "b", "local_path": "/tmp/b"})

    response = client.get("/api/v1/workspaces")
    assert response.status_code == 200
    body = response.json()
    names = sorted(item["name"] for item in body["items"])
    assert names == ["a", "b"]
    for item in body["items"]:
        assert "source_type" not in item
        assert "source_value" not in item


def test_list_workspaces_empty(client: TestClient) -> None:
    response = client.get("/api/v1/workspaces")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_get_workspace_by_id(client: TestClient) -> None:
    create = client.post(
        "/api/v1/workspaces",
        json={"name": "demo", "local_path": "/tmp/demo"},
    ).json()

    response = client.get(f"/api/v1/workspaces/{create['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == create["id"]
    assert body["name"] == "demo"
    assert body["local_path"] == "/tmp/demo"
    assert body["status"] == "created"


def test_get_workspace_unknown_id_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/workspaces/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "WORKSPACE_NOT_FOUND"
    assert "does-not-exist" in body["error"]["message"]
