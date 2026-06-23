import asyncio
import json

from vibing_harness import CommandResult
from vibing_harness.descriptors.cursor import CursorDescriptor
from .fakes import FakeExecutor


def test_install_runs_curl_bash():
    ex = FakeExecutor()
    asyncio.run(CursorDescriptor().install(ex))
    assert ex.runs[0] == ["bash", "-c", "curl https://cursor.com/install -fsS | bash"]


def test_is_authenticated_false_without_key_file():
    assert asyncio.run(CursorDescriptor().is_authenticated(FakeExecutor())) is False


def test_write_then_authenticated_and_spawn_env():
    ex = FakeExecutor()
    d = CursorDescriptor()
    asyncio.run(d.write_credentials(ex, {"api_key": "key-123"}))
    assert json.loads(ex.files[".config/vibing-harness/cursor.json"]) == {"api_key": "key-123"}
    assert ex.modes[".config/vibing-harness/cursor.json"] == 0o600
    assert asyncio.run(d.is_authenticated(ex)) is True
    assert asyncio.run(d.spawn_env(ex)) == {"CURSOR_API_KEY": "key-123"}


def test_spawn_env_empty_without_key():
    assert asyncio.run(CursorDescriptor().spawn_env(FakeExecutor())) == {}


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
