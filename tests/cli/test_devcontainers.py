import json

import httpx
from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()

_DC = {
    "id": "dc_1",
    "name": "sandbox",
    "local_path": "/p",
    "status": "created",
    "created_at": "t",
    "updated_at": "t",
}


def test_add_posts_name_and_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json=_DC)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "add", "sandbox", "-d", "/p"])

    assert result.exit_code == 0, result.output
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/devcontainers"
    assert seen["body"] == {"name": "sandbox", "local_path": "/p"}


def test_ls_renders_table(patch_api) -> None:
    patch_api(lambda request: httpx.Response(200, json={"items": [_DC]}))
    result = runner.invoke(app, ["devcontainer", "ls"])
    assert result.exit_code == 0, result.output
    assert "sandbox" in result.output


def test_get_json(patch_api) -> None:
    patch_api(lambda request: httpx.Response(200, json=_DC))
    result = runner.invoke(app, ["devcontainer", "get", "dc_1", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["id"] == "dc_1"


def test_update_sends_only_set_fields(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_DC)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "update", "dc_1", "--name", "new"])
    assert result.exit_code == 0, result.output
    assert seen["method"] == "PATCH"
    assert seen["body"] == {"name": "new"}


def test_rm_calls_delete(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(204)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "rm", "dc_1"])
    assert result.exit_code == 0, result.output
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/api/v1/devcontainers/dc_1"


def test_update_requires_a_field(patch_api) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=_DC)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "update", "dc_1"])
    assert result.exit_code != 0
    assert not called


def test_start_posts_to_start(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(202, json=_DC)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "start", "dc_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/start"


def test_stop_posts_to_stop(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(202, json=_DC)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "stop", "dc_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/stop"
