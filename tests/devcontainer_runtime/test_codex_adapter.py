import asyncio
import json
from pathlib import Path

from vibing_devcontainer_runtime.harness.codex import CodexAdapter
from vibing_devcontainer_runtime.harness.process import CompletedCommand, HarnessProcess


class FakeProcess(HarnessProcess):
    def __init__(self, result: CompletedCommand) -> None:
        self._result = result

    async def wait(self) -> CompletedCommand:
        return self._result

    async def terminate(self) -> None:
        pass


def make_factory(by_argv):
    calls = []

    def factory(argv, cwd, env):
        calls.append((argv, cwd, env))
        return FakeProcess(by_argv(argv))

    factory.calls = calls  # type: ignore[attr-defined]
    return factory


def test_name():
    assert (
        CodexAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), Path("/tmp")).name
        == "codex"
    )


def test_is_installed_true_on_version_exit_zero(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "codex 1.2.3", ""))
    adapter = CodexAdapter(factory, tmp_path)
    assert asyncio.run(adapter.is_installed()) is True
    assert factory.calls[0][0] == ["codex", "--version"]


def test_is_installed_false_when_missing(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(127, "", "not found"))
    assert asyncio.run(CodexAdapter(factory, tmp_path).is_installed()) is False


def test_is_authenticated_uses_login_status_exit_code(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "Logged in", ""))
    adapter = CodexAdapter(factory, tmp_path)
    assert asyncio.run(adapter.is_authenticated()) is True
    assert factory.calls[0][0] == ["codex", "login", "status"]


def test_write_credentials_writes_auth_json_0600(tmp_path):
    adapter = CodexAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    adapter.write_credentials({"auth_json": {"OPENAI_API_KEY": "sk-test"}})
    path = tmp_path / ".codex" / "auth.json"
    assert json.loads(path.read_text()) == {"OPENAI_API_KEY": "sk-test"}
    assert (path.stat().st_mode & 0o777) == 0o600


def test_build_spawn_argv_is_fully_autonomous(tmp_path):
    adapter = CodexAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    argv = adapter.build_spawn_argv("gpt-5.4", "fix the bug")
    assert argv == [
        "codex",
        "exec",
        "--model",
        "gpt-5.4",
        "--dangerously-bypass-approvals-and-sandbox",
        "fix the bug",
    ]


def test_install_runs_npm_global(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "", ""))
    asyncio.run(CodexAdapter(factory, tmp_path).install())
    assert factory.calls[0][0] == ["npm", "install", "-g", "@openai/codex"]


def test_extract_result_returns_trimmed_stdout(tmp_path):
    adapter = CodexAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    assert adapter.extract_result("  final answer\n") == "final answer"
