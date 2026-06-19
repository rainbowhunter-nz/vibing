import asyncio
import json

from vibing_devcontainer_runtime.harness.cursor import CursorAdapter
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


def test_name(tmp_path):
    assert (
        CursorAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path).name
        == "cursor"
    )


def test_is_installed_checks_version(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "1.0", ""))
    adapter = CursorAdapter(factory, tmp_path)
    assert asyncio.run(adapter.is_installed()) is True
    assert factory.calls[0][0] == ["cursor-agent", "--version"]


def test_write_credentials_then_authenticated_and_env(tmp_path):
    adapter = CursorAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    assert asyncio.run(adapter.is_authenticated()) is False
    adapter.write_credentials({"api_key": "key-123"})
    path = tmp_path / ".config" / "vibing-harness" / "cursor.json"
    assert json.loads(path.read_text()) == {"api_key": "key-123"}
    assert (path.stat().st_mode & 0o777) == 0o600
    assert asyncio.run(adapter.is_authenticated()) is True
    assert adapter.spawn_env() == {"CURSOR_API_KEY": "key-123"}


def test_build_spawn_argv_print_force_text(tmp_path):
    adapter = CursorAdapter(make_factory(lambda a: CompletedCommand(0, "", "")), tmp_path)
    argv = adapter.build_spawn_argv("sonnet-4", "do it")
    assert argv == [
        "cursor-agent",
        "-p",
        "do it",
        "--model",
        "sonnet-4",
        "--force",
        "--output-format",
        "text",
    ]


def test_install_runs_curl_pipe_bash(tmp_path):
    factory = make_factory(lambda argv: CompletedCommand(0, "", ""))
    asyncio.run(CursorAdapter(factory, tmp_path).install())
    argv = factory.calls[0][0]
    assert argv[0] == "bash" and "cursor.com/install" in " ".join(argv)
