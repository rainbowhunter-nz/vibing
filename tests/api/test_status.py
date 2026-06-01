from fastapi.testclient import TestClient


def test_status_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_status_includes_service_and_version(client: TestClient) -> None:
    response = client.get("/api/v1/status")
    body = response.json()
    assert body["service"] == "vibing-api"
    assert isinstance(body["version"], str) and body["version"]
