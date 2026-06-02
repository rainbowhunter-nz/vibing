import httpx
import pytest
import typer
from typer.testing import CliRunner

from vibing_cli import app
from vibing_cli.client import http

runner = CliRunner()


def test_base_url_default() -> None:
    assert http.base_url() == "http://localhost:8080/api/v1"


def test_configure_strips_trailing_slash() -> None:
    http.configure("http://host.docker.internal:9000/", "/api/v1")
    assert http.base_url() == "http://host.docker.internal:9000/api/v1"


def test_env_var_sets_base_url(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"items": []})

    patch_api(handler)
    result = runner.invoke(
        app, ["devcontainer", "ls"], env={"VIBING_API_URL": "http://example.test:9000"}
    )
    assert result.exit_code == 0, result.output
    assert seen["url"] == "http://example.test:9000/api/v1/devcontainers"


def test_request_returns_json_on_success(patch_api) -> None:
    patch_api(lambda request: httpx.Response(200, json={"ok": True}))
    assert http.request("GET", "/status") == {"ok": True}


def test_request_returns_none_on_204(patch_api) -> None:
    patch_api(lambda request: httpx.Response(204))
    assert http.request("DELETE", "/devcontainers/x") is None


def test_request_raises_exit_on_error_envelope(
    patch_api, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_api(
        lambda request: httpx.Response(
            404,
            json={"error": {"code": "DEVCONTAINER_NOT_FOUND", "message": "nope", "details": None}},
        )
    )
    with pytest.raises(typer.Exit) as exc:
        http.request("GET", "/devcontainers/x")
    assert exc.value.exit_code == 1
    assert "DEVCONTAINER_NOT_FOUND" in capsys.readouterr().err


def test_request_raises_exit_on_connect_error(
    patch_api, capsys: pytest.CaptureFixture[str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    patch_api(handler)
    with pytest.raises(typer.Exit) as exc:
        http.request("GET", "/status")
    assert exc.value.exit_code == 1
    assert "Cannot reach API" in capsys.readouterr().err
