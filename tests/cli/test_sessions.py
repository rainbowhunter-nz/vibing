import json

import httpx
from typer.testing import CliRunner

from vibing_cli import app

runner = CliRunner()

_SESSION = {
    "id": "as_1",
    "devcontainer_id": "dc_1",
    "status": "starting",
    "started_at": None,
    "ended_at": None,
    "last_event_at": None,
    "created_at": "t",
    "updated_at": "t",
}


def test_session_start_posts_prompt(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json=_SESSION)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "session", "start", "dc_1", "-p", "do it"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/agent-sessions"
    assert seen["body"] == {"prompt": "do it"}


def test_session_input_body(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json=_SESSION)

    patch_api(handler)
    result = runner.invoke(
        app,
        [
            "devcontainer",
            "session",
            "input",
            "dc_1",
            "as_1",
            "--inbox-event",
            "ib_1",
            "--text",
            "yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/agent-sessions/as_1/user-input"
    assert seen["body"] == {"inbox_event_id": "ib_1", "text": "yes"}


def test_session_resolve_body(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(202, json=_SESSION)

    patch_api(handler)
    result = runner.invoke(
        app,
        [
            "devcontainer",
            "session",
            "resolve",
            "dc_1",
            "as_1",
            "--approval",
            "ap_1",
            "--resolution",
            "approved",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/agent-sessions/as_1/approval-resolution"
    assert seen["body"] == {"approval_request_id": "ap_1", "resolution": "approved"}


def test_session_resolve_rejects_bad_value(patch_api) -> None:
    patch_api(lambda request: httpx.Response(202, json=_SESSION))
    result = runner.invoke(
        app,
        [
            "devcontainer",
            "session",
            "resolve",
            "dc_1",
            "as_1",
            "--approval",
            "ap_1",
            "--resolution",
            "maybe",
        ],
    )
    assert result.exit_code != 0


def test_session_stop_path(patch_api) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(202, json=_SESSION)

    patch_api(handler)
    result = runner.invoke(app, ["devcontainer", "session", "stop", "dc_1", "as_1"])
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/api/v1/devcontainers/dc_1/agent-sessions/as_1/stop"
