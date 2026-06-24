import asyncio
from collections.abc import AsyncIterator

from vibing_api.core.devcontainer_executor import DevcontainerExecutor


def _fake_runner(script: dict[str, bytes]):
    calls: list[tuple[list[str], bytes | None]] = []

    async def runner(argv: list[str], stdin: bytes | None) -> AsyncIterator[bytes]:
        calls.append((argv, stdin))
        # key on the in-container command (everything after `exec --workspace-folder <path>`)
        key = " ".join(argv[4:])
        for k, out in script.items():
            if k in key:
                yield out
                return
        yield b""

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def test_run_collects_combined_output_and_zero_rc():
    runner = _fake_runner({"codex --version": b"codex 1.2.3\n__rc=0__"})
    ex = DevcontainerExecutor("/work", runner=runner)
    result = asyncio.run(ex.run(["codex", "--version"]))
    assert result.returncode == 0
    assert "codex 1.2.3" in result.stdout
    argv = runner.calls[0][0]
    assert argv[:4] == ["devcontainer", "exec", "--workspace-folder", "/work"]
    assert "codex --version" in argv[-1]


def test_run_injects_env_into_shell():
    runner = _fake_runner({"cursor-agent models": b"ok\n__rc=0__"})
    ex = DevcontainerExecutor("/work", runner=runner)
    result = asyncio.run(ex.run(["cursor-agent", "models"], env={"CURSOR_API_KEY": "k 1"}))
    assert result.returncode == 0
    shell = runner.calls[0][0][-1]
    assert "CURSOR_API_KEY='k 1' cursor-agent models" in shell


def test_write_pipes_blob_to_stdin_with_umask_and_home_path():
    runner = _fake_runner({})
    ex = DevcontainerExecutor("/work", runner=runner)
    asyncio.run(ex.write(".codex/auth.json", b'{"k":1}', mode=0o600))
    argv, stdin = runner.calls[0]
    assert stdin == b'{"k":1}'
    shell = argv[-1]
    assert "umask 177" in shell
    assert "$HOME/.codex/auth.json" in shell
    assert "cat >" in shell


def test_read_returns_bytes_and_none_when_absent():
    runner = _fake_runner(
        {'cat "$HOME/.config/vibing-harness/cursor.json"': b'{"api_key":"x"}\n__rc=0__'}
    )
    ex = DevcontainerExecutor("/work", runner=runner)
    got = asyncio.run(ex.read(".config/vibing-harness/cursor.json"))
    assert got == b'{"api_key":"x"}'

    # absent file: non-zero rc → None
    absent_runner = _fake_runner(
        {'cat "$HOME/missing.txt"': b"cat: missing.txt: No such file\n__rc=1__"}
    )
    ex2 = DevcontainerExecutor("/work", runner=absent_runner)
    assert asyncio.run(ex2.read("missing.txt")) is None


def test_stream_yields_lines():
    runner = _fake_runner({"npm install": b"added 1 package\nok\n"})
    ex = DevcontainerExecutor("/work", runner=runner)

    async def collect():
        return [line async for line in ex.stream(["npm", "install", "-g", "@openai/codex"])]

    lines = asyncio.run(collect())
    assert "added 1 package" in lines[0]
