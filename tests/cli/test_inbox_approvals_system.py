import httpx
from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()


def test_inbox_ls_passes_filters(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    patch_api(handler)
    result = runner.invoke(app, ["inbox", "ls", "--status", "pending", "--devcontainer", "dc_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/inbox-events"
    assert seen["params"] == {"status": "pending", "devcontainer_id": "dc_1"}


def test_inbox_get_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"id": "ib_1"})

    patch_api(handler)
    result = runner.invoke(app, ["inbox", "get", "ib_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/inbox-events/ib_1"


def test_approval_ls_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"items": []})

    patch_api(handler)
    result = runner.invoke(app, ["approval", "ls"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/approval-requests"


def test_approval_get_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"id": "ap_1"})

    patch_api(handler)
    result = runner.invoke(app, ["approval", "get", "ap_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/approval-requests/ap_1"


def test_system_status_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"status": "ok"})

    patch_api(handler)
    result = runner.invoke(app, ["system", "status"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/status"


def test_system_health_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"status": "ok"})

    patch_api(handler)
    result = runner.invoke(app, ["system", "health"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/health"
