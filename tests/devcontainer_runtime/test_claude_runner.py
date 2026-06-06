"""Tests for ClaudeCodeRunner — fake runner, no real subprocess."""

import asyncio

from vibing_devcontainer_runtime.claude_runner import (
    ClaudeCodeRunner,
    ClaudeFailure,
    ClaudeSuccess,
    RunResult,
)


def _run(runner: ClaudeCodeRunner, prompt: str):
    return asyncio.run(runner.run(prompt))


def _make_fake_runner(returncode: int, stdout: str = "", stderr: str = ""):
    async def fake(command: list[str]) -> RunResult:
        return RunResult(returncode=returncode, stdout=stdout, stderr=stderr)

    return fake


def _make_raising_runner(exc: Exception):
    async def fake(command: list[str]) -> RunResult:
        raise exc

    return fake


# --- Invocation built correctly ---


def test_invocation_contains_prompt():
    captured: list[list[str]] = []

    async def fake(command: list[str]) -> RunResult:
        captured.append(command)
        return RunResult(returncode=0, stdout="ok", stderr="")

    runner = ClaudeCodeRunner(runner=fake)
    _run(runner, "hello world")
    assert captured[0] == [
        "claude",
        "-p",
        "hello world",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
    ]


def test_custom_binary_used_in_invocation():
    captured: list[list[str]] = []

    async def fake(command: list[str]) -> RunResult:
        captured.append(command)
        return RunResult(returncode=0, stdout="", stderr="")

    runner = ClaudeCodeRunner(binary="my-claude", runner=fake)
    _run(runner, "test")
    assert captured[0][0] == "my-claude"


# --- Exit 0 → ClaudeSuccess ---


def test_exit_zero_returns_success():
    runner = ClaudeCodeRunner(runner=_make_fake_runner(0, stdout='{"result":"done"}'))
    result = _run(runner, "do something")
    assert isinstance(result, ClaudeSuccess)
    assert result.result == "done"


def test_exit_zero_parses_full_claude_result_envelope():
    stdout = (
        '{"type":"result","subtype":"success","is_error":false,'
        '"result":"Hi! How can I help you today?","stop_reason":"end_turn"}'
    )
    runner = ClaudeCodeRunner(runner=_make_fake_runner(0, stdout=stdout))
    result = _run(runner, "hi")
    assert isinstance(result, ClaudeSuccess)
    assert result.result == "Hi! How can I help you today?"


# --- Non-zero exit → ClaudeFailure ---


def test_nonzero_exit_returns_failure():
    runner = ClaudeCodeRunner(runner=_make_fake_runner(1, stderr="some error output"))
    result = _run(runner, "fail")
    assert isinstance(result, ClaudeFailure)
    assert result.exit_code == 1
    assert "some error output" in result.stderr_tail


def test_nonzero_exit_stderr_tail_bounded():
    long_stderr = "x" * 10000
    runner = ClaudeCodeRunner(runner=_make_fake_runner(2, stderr=long_stderr))
    result = _run(runner, "fail")
    assert isinstance(result, ClaudeFailure)
    assert len(result.stderr_tail) <= 4000


# --- Missing binary → ClaudeFailure (not a crash) ---


def test_missing_binary_returns_failure_not_crash():
    runner = ClaudeCodeRunner(runner=_make_raising_runner(FileNotFoundError("no claude")))
    result = _run(runner, "anything")
    assert isinstance(result, ClaudeFailure)
    assert result.exit_code is None
    assert "claude binary not found" in result.message


def test_missing_binary_does_not_raise():
    runner = ClaudeCodeRunner(runner=_make_raising_runner(FileNotFoundError()))
    # Should not raise
    result = _run(runner, "x")
    assert isinstance(result, ClaudeFailure)


# --- session_id flag ---


def test_session_id_appended_when_provided():
    captured: list[list[str]] = []

    async def fake(command: list[str]) -> RunResult:
        captured.append(command)
        return RunResult(returncode=0, stdout="ok", stderr="")

    runner = ClaudeCodeRunner(runner=fake)
    asyncio.run(runner.run("hello", session_id="my-session-uuid"))
    assert captured[0] == [
        "claude",
        "-p",
        "hello",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--session-id",
        "my-session-uuid",
    ]


def test_no_session_id_omitted():
    captured: list[list[str]] = []

    async def fake(command: list[str]) -> RunResult:
        captured.append(command)
        return RunResult(returncode=0, stdout="ok", stderr="")

    runner = ClaudeCodeRunner(runner=fake)
    asyncio.run(runner.run("hello"))
    assert "--session-id" not in captured[0]


# --- resume flag (ADR-0008: `claude -p <prompt> --resume <id>`) ---


def test_resume_appends_resume_flag_not_session_id():
    captured: list[list[str]] = []

    async def fake(command: list[str]) -> RunResult:
        captured.append(command)
        return RunResult(returncode=0, stdout="ok", stderr="")

    runner = ClaudeCodeRunner(runner=fake)
    asyncio.run(runner.run("follow up", session_id="my-session-uuid", resume=True))
    assert captured[0] == [
        "claude",
        "-p",
        "follow up",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--resume",
        "my-session-uuid",
    ]
    assert "--session-id" not in captured[0]
    assert "--fork-session" not in captured[0]
