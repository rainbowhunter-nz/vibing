import json

import httpx
from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()

_HARNESS = {"name": "claude-code", "status": "idle"}
_CRED_VIEW = {"name": "claude-code", "configured": True}


def test_ls_lists_harnesses(patch_api) -> None:
    patch_api(lambda request: httpx.Response(200, json=[_HARNESS]))
    result = runner.invoke(app, ["harness", "ls", "dc_1"])
    assert result.exit_code == 0, result.output


def test_authenticate_posts_to_authenticate(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json=_HARNESS)

    patch_api(handler)
    result = runner.invoke(app, ["harness", "authenticate", "dc_1", "claude-code"])
    assert result.exit_code == 0, result.output
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v1/devcontainers/dc_1/harnesses/claude-code/authenticate"


def test_creds_set_sends_blob_body(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_CRED_VIEW)

    patch_api(handler)
    result = runner.invoke(
        app,
        ["harness", "creds", "set", "claude-code", "--blob", '{"token": "abc"}'],
    )
    assert result.exit_code == 0, result.output
    assert seen["method"] == "PUT"
    assert seen["path"] == "/api/v1/settings/harness-credentials/claude-code"
    assert seen["body"] == {"blob": {"token": "abc"}}


def test_creds_set_rejects_invalid_json(patch_api) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=_CRED_VIEW)

    patch_api(handler)
    result = runner.invoke(
        app,
        ["harness", "creds", "set", "claude-code", "--blob", "not-json"],
    )
    assert result.exit_code != 0
    assert not called
