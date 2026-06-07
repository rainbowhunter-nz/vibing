"""Tests for ClaudeCodeRunner — streaming via the injectable StreamRunner seam.

No real subprocess: the fake StreamRunner yields a SEQUENCE of stream-json lines
(deltas), and the terminal `result` line drives the success/failure mapping (ADR-0010).
"""

import asyncio
import json
from collections.abc import AsyncIterator

from vibing_protocol import RunEndedDelta, RunStartedDelta, TextDelta, TurnDelta

from vibing_devcontainer_runtime.claude_runner import (
    ClaudeCodeRunner,
    ClaudeFailure,
    ClaudeSuccess,
)


def _lines_runner(lines: list[str]):
    async def runner(command: list[str]) -> AsyncIterator[str]:
        for line in lines:
            yield line

    return runner


def _raising_runner(exc: Exception):
    async def runner(command: list[str]) -> AsyncIterator[str]:
        raise exc
        yield ""  # pragma: no cover — makes this an async generator

    return runner


def _collect(runner: ClaudeCodeRunner, prompt: str, **kw):
    deltas: list[TurnDelta] = []

    async def on_delta(d: TurnDelta) -> None:
        deltas.append(d)

    result = asyncio.run(runner.start(prompt, **kw).wait(on_delta))
    return result, deltas


_INIT = json.dumps({"type": "system", "subtype": "init", "session_id": "s"})


def _msg_start(mid: str) -> str:
    return json.dumps(
        {"type": "stream_event", "event": {"type": "message_start", "message": {"id": mid}}}
    )


def _text(text: str) -> str:
    return json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": text},
            },
        }
    )


def _result(result: str = "done", is_error: bool = False) -> str:
    return json.dumps(
        {"type": "result", "subtype": "success", "is_error": is_error, "result": result}
    )


# --- Command building (stream-json; resume/session-id unchanged from ADR-0008) ---


def test_invocation_uses_stream_json_flags():
    captured: list[list[str]] = []

    async def runner(command: list[str]) -> AsyncIterator[str]:
        captured.append(command)
        for line in [_result()]:
            yield line

    rnr = ClaudeCodeRunner(runner=runner)
    _collect(rnr, "hello world")
    assert captured[0] == [
        "claude",
        "-p",
        "hello world",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--permission-mode",
        "bypassPermissions",
    ]


def test_session_id_appended_when_provided():
    captured: list[list[str]] = []

    async def runner(command: list[str]) -> AsyncIterator[str]:
        captured.append(command)
        for line in [_result()]:
            yield line

    rnr = ClaudeCodeRunner(runner=runner)
    asyncio.run(rnr.start("hi", session_id="sid").wait(lambda d: asyncio.sleep(0)))
    assert captured[0][-2:] == ["--session-id", "sid"]
    assert "--resume" not in captured[0]


def test_resume_appends_resume_flag_not_session_id():
    captured: list[list[str]] = []

    async def runner(command: list[str]) -> AsyncIterator[str]:
        captured.append(command)
        for line in [_result()]:
            yield line

    rnr = ClaudeCodeRunner(runner=runner)
    asyncio.run(rnr.start("hi", session_id="sid", resume=True).wait(lambda d: asyncio.sleep(0)))
    assert captured[0][-2:] == ["--resume", "sid"]
    assert "--session-id" not in captured[0]
    assert "--fork-session" not in captured[0]


# --- Deltas surface in order ---


def test_deltas_surface_in_order():
    runner = ClaudeCodeRunner(
        runner=_lines_runner(
            [_INIT, _msg_start("msg_1"), _text("Hel"), _text("lo"), _result("Hello")]
        )
    )
    result, deltas = _collect(runner, "hi")
    assert deltas == [
        RunStartedDelta(),
        TextDelta(turn_id="msg_1", text="Hel"),
        TextDelta(turn_id="msg_1", text="lo"),
        RunEndedDelta(),
    ]
    assert isinstance(result, ClaudeSuccess)
    assert result.result == "Hello"


# --- Terminal result maps to success/failure ---


def test_terminal_result_success_maps_to_claude_success():
    runner = ClaudeCodeRunner(runner=_lines_runner([_INIT, _result("the answer")]))
    result, _ = _collect(runner, "hi")
    assert isinstance(result, ClaudeSuccess)
    assert result.result == "the answer"


def test_terminal_result_error_maps_to_claude_failure():
    runner = ClaudeCodeRunner(runner=_lines_runner([_INIT, _result(result="", is_error=True)]))
    result, _ = _collect(runner, "hi")
    assert isinstance(result, ClaudeFailure)


def test_no_terminal_result_is_failure():
    """Stream ended without a result event -> failure (the run did not complete)."""
    runner = ClaudeCodeRunner(runner=_lines_runner([_INIT, _msg_start("m"), _text("partial")]))
    result, _ = _collect(runner, "hi")
    assert isinstance(result, ClaudeFailure)


# --- Missing binary -> failure, not a crash ---


def test_missing_binary_returns_failure_not_crash():
    runner = ClaudeCodeRunner(runner=_raising_runner(FileNotFoundError("no claude")))
    result, deltas = _collect(runner, "x")
    assert isinstance(result, ClaudeFailure)
    assert result.exit_code is None
    assert "claude binary not found" in result.message
    assert deltas == []
