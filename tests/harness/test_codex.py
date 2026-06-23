import asyncio
import json

from vibing_harness import CommandResult
from vibing_harness.descriptors.codex import CodexDescriptor
from .fakes import FakeExecutor


def test_is_installed_true_on_version_zero():
    ex = FakeExecutor({"codex": CommandResult(0, "codex 1.2.3", "")})
    assert asyncio.run(CodexDescriptor().is_installed(ex)) is True
    assert ex.runs[0] == ["codex", "--version"]


def test_is_installed_false_when_missing():
    ex = FakeExecutor({"codex": CommandResult(127, "", "not found")})
    assert asyncio.run(CodexDescriptor().is_installed(ex)) is False


def test_install_runs_npm_global():
    ex = FakeExecutor()
    asyncio.run(CodexDescriptor().install(ex))
    assert ex.runs[0] == ["npm", "install", "-g", "@openai/codex"]


def test_is_authenticated_uses_login_status():
    ex = FakeExecutor({"codex": CommandResult(0, "Logged in", "")})
    assert asyncio.run(CodexDescriptor().is_authenticated(ex)) is True
    assert ex.runs[0] == ["codex", "login", "status"]


def test_write_credentials_writes_home_relative_auth_json():
    ex = FakeExecutor()
    asyncio.run(CodexDescriptor().write_credentials(ex, {"auth_json": {"OPENAI_API_KEY": "sk"}}))
    assert json.loads(ex.files[".codex/auth.json"]) == {"OPENAI_API_KEY": "sk"}
    assert ex.modes[".codex/auth.json"] == 0o600


def test_build_spawn_argv_is_fully_autonomous():
    argv = CodexDescriptor().build_spawn_argv("gpt-5.4", "fix it")
    assert argv == [
        "codex",
        "exec",
        "--model",
        "gpt-5.4",
        "--dangerously-bypass-approvals-and-sandbox",
        "fix it",
    ]


def test_extract_result_trims():
    assert CodexDescriptor().extract_result("  done\n") == "done"
