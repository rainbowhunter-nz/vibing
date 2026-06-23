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


def test_write_pipes_blob_to_stdin_with_umask_and_home_path():
    runner = _fake_runner({})
    ex = DevcontainerExecutor("/work", runner=runner)
    asyncio.run(ex.write(".codex/auth.json", b'{"k":1}', mode=0o600))
    argv, stdin = runner.calls[0]
    assert stdin == b'{"k":1}'
    shell = argv[-1]
    assert "umask 077" in shell
    assert "$HOME/.codex/auth.json" in shell
    assert "cat >" in shell


def test_read_returns_bytes_and_none_when_absent():
    runner = _fake_runner(
        {'cat "$HOME/.config/vibing-harness/cursor.json"': b'{"api_key":"x"}\n__rc=0__'}
    )
    ex = DevcontainerExecutor("/work", runner=runner)
    got = asyncio.run(ex.read(".config/vibing-harness/cursor.json"))
    assert got == b'{"api_key":"x"}'


def test_stream_yields_lines():
    runner = _fake_runner({"npm install": b"added 1 package\nok\n"})
    ex = DevcontainerExecutor("/work", runner=runner)

    async def collect():
        return [line async for line in ex.stream(["npm", "install", "-g", "@openai/codex"])]

    lines = asyncio.run(collect())
    assert "added 1 package" in lines[0]
