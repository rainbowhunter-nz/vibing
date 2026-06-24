import asyncio
import json

from vibing_harness import CommandResult
from vibing_harness.descriptors.cursor import CursorDescriptor
from .fakes import FakeExecutor


def test_install_runs_curl_bash():
    ex = FakeExecutor()
    asyncio.run(CursorDescriptor().install(ex))
    assert ex.runs[0] == ["bash", "-c", "curl https://cursor.com/install -fsS | bash"]


_LOGGED_IN = {"cursor-agent status": CommandResult(0, '{"isAuthenticated": true}', "")}
_LOGGED_OUT = {"cursor-agent status": CommandResult(0, '{"isAuthenticated": false}', "")}


def test_write_credentials_persists_api_key():
    ex = FakeExecutor()
    asyncio.run(CursorDescriptor().write_credentials(ex, {"api_key": "key-123"}))
    assert json.loads(ex.files[".config/vibing-harness/cursor.json"]) == {"api_key": "key-123"}
    assert ex.modes[".config/vibing-harness/cursor.json"] == 0o600


def test_is_authenticated_true_when_logged_in_subscription():
    ex = FakeExecutor(_LOGGED_IN)
    assert asyncio.run(CursorDescriptor().is_authenticated(ex)) is True
    # subscription path wins: no metered api-key probe
    assert ["cursor-agent", "models"] not in ex.runs


def test_is_authenticated_via_api_key_when_logged_out():
    ex = FakeExecutor(_LOGGED_OUT)
    d = CursorDescriptor()
    asyncio.run(d.write_credentials(ex, {"api_key": "key-123"}))
    assert asyncio.run(d.is_authenticated(ex)) is True
    # falls back to validating the stored key via the key-honoring command
    assert ex.runs[-1] == ["cursor-agent", "models"]
    assert ex.run_envs[-1] == {"CURSOR_API_KEY": "key-123"}


def test_is_authenticated_false_when_api_key_invalid():
    ex = FakeExecutor({**_LOGGED_OUT, "cursor-agent models": CommandResult(1, "", "auth required")})
    d = CursorDescriptor()
    asyncio.run(d.write_credentials(ex, {"api_key": "stale-key"}))
    assert asyncio.run(d.is_authenticated(ex)) is False


def test_is_authenticated_false_without_login_or_key():
    ex = FakeExecutor(_LOGGED_OUT)
    assert asyncio.run(CursorDescriptor().is_authenticated(ex)) is False
    assert ["cursor-agent", "models"] not in ex.runs  # no key → no probe


def test_spawn_env_prefers_subscription_over_api_key():
    ex = FakeExecutor(_LOGGED_IN)
    d = CursorDescriptor()
    asyncio.run(d.write_credentials(ex, {"api_key": "key-123"}))
    assert asyncio.run(d.spawn_env(ex)) == {}


def test_spawn_env_injects_api_key_when_logged_out():
    ex = FakeExecutor(_LOGGED_OUT)
    d = CursorDescriptor()
    asyncio.run(d.write_credentials(ex, {"api_key": "key-123"}))
    assert asyncio.run(d.spawn_env(ex)) == {"CURSOR_API_KEY": "key-123"}


def test_spawn_env_empty_without_login_or_key():
    assert asyncio.run(CursorDescriptor().spawn_env(FakeExecutor(_LOGGED_OUT))) == {}


def test_build_spawn_argv():
    argv = CursorDescriptor().build_spawn_argv("auto", "do it")
    assert argv == [
        "cursor-agent",
        "-p",
        "do it",
        "--model",
        "auto",
        "--force",
        "--output-format",
        "text",
    ]


def test_is_installed_checks_version():
    ex = FakeExecutor({"cursor-agent": CommandResult(0, "1.0", "")})
    assert asyncio.run(CursorDescriptor().is_installed(ex)) is True
    assert ex.runs[0] == ["cursor-agent", "--version"]
