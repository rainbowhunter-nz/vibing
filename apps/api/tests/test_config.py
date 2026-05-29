from fastapi.testclient import TestClient


def test_config_returns_api_prefix(client: TestClient) -> None:
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    body = response.json()
    assert body["api_v1_prefix"] == "/api/v1"


def test_config_does_not_leak_database_url(client: TestClient) -> None:
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    body = response.json()
    # Backend-only values must not be exposed to the frontend.
    assert "database_url" not in body
