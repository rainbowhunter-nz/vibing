from fastapi.testclient import TestClient


def _assert_error_shape(body: dict) -> None:
    assert "error" in body
    error = body["error"]
    assert isinstance(error.get("code"), str) and error["code"]
    assert isinstance(error.get("message"), str) and error["message"]
    # details is optional but the key should exist (may be null)
    assert "details" in error


def test_validation_error_uses_standard_shape(client: TestClient) -> None:
    response = client.post("/api/v1/devcontainers", json={})
    assert response.status_code == 422
    body = response.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == "VALIDATION_ERROR"
    # details should describe which fields failed
    assert body["error"]["details"] is not None


def test_devcontainer_not_found_uses_standard_shape(client: TestClient) -> None:
    response = client.get("/api/v1/devcontainers/missing")
    assert response.status_code == 404
    body = response.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == "DEVCONTAINER_NOT_FOUND"
