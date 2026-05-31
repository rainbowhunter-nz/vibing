"""Tests for AgentCommandHandler — fake runner, no real subprocess."""

import asyncio

from vibing_devcontainer_runtime.claude_runner import (
    ClaudeCodeRunner,
    ClaudeFailure,
    ClaudeSuccess,
    RunResult,
)
from vibing_devcontainer_runtime.command_handler import AgentCommandHandler
from vibing_protocol import Command, RuntimeEvent


def _make_command(
    type_: str = "start_agent_session",
    devcontainer_id: str = "dc-1",
    agent_session_id: str = "sess-1",
    payload: dict | None = None,
) -> Command:
    return Command(
        type=type_,  # type: ignore[arg-type]
        devcontainer_id=devcontainer_id,
        agent_session_id=agent_session_id,
        payload=payload or {"prompt": "hello"},
    )


def _make_runner(result: ClaudeSuccess | ClaudeFailure) -> ClaudeCodeRunner:
    async def fake(command: list[str]) -> RunResult:
        if isinstance(result, ClaudeFailure) and result.exit_code is not None:
            return RunResult(returncode=result.exit_code, stdout="", stderr=result.stderr_tail)
        if isinstance(result, ClaudeSuccess):
            return RunResult(returncode=0, stdout=result.result, stderr="")
        # FileNotFoundError path handled by separate fixture
        return RunResult(returncode=0, stdout="", stderr="")

    return ClaudeCodeRunner(runner=fake)


async def _collect_events(handler: AgentCommandHandler, command: Command) -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    await handler.handle(command, emit)
    # Allow background tasks to complete
    await asyncio.gather(*handler._tasks)
    return events


# --- agent_session_started emitted immediately ---


def test_start_emits_agent_session_started():
    runner = _make_runner(ClaudeSuccess(result="done"))
    handler = AgentCommandHandler(runner)
    events = asyncio.run(_collect_events(handler, _make_command()))
    assert events[0].event_type == "agent_session_started"
    assert events[0].source == "devcontainer_runtime_agent"
    assert events[0].devcontainer_id == "dc-1"
    assert events[0].agent_session_id == "sess-1"


# --- session_completed on success ---


def test_start_success_emits_session_completed():
    runner = _make_runner(ClaudeSuccess(result="output text"))
    handler = AgentCommandHandler(runner)
    events = asyncio.run(_collect_events(handler, _make_command()))
    types = [e.event_type for e in events]
    assert "session_completed" in types
    completed = next(e for e in events if e.event_type == "session_completed")
    assert completed.payload == {"result": "output text"}
    assert completed.agent_session_id == "sess-1"
    assert completed.devcontainer_id == "dc-1"


# --- session_failed on non-zero exit ---


def test_start_failure_emits_session_failed():
    runner = _make_runner(ClaudeFailure(exit_code=1, stderr_tail="boom", message="failed"))
    handler = AgentCommandHandler(runner)
    events = asyncio.run(_collect_events(handler, _make_command()))
    types = [e.event_type for e in events]
    assert "session_failed" in types
    failed = next(e for e in events if e.event_type == "session_failed")
    assert failed.payload is not None
    assert failed.payload["exit_code"] == 1
    assert failed.payload["stderr_tail"] == "boom"
    assert failed.agent_session_id == "sess-1"
    assert failed.devcontainer_id == "dc-1"


# --- session_failed when binary is missing ---


def test_start_missing_binary_emits_session_failed_not_crash():
    async def raising_runner(command: list[str]) -> RunResult:
        raise FileNotFoundError("no claude")

    runner = ClaudeCodeRunner(runner=raising_runner)
    handler = AgentCommandHandler(runner)
    events = asyncio.run(_collect_events(handler, _make_command()))
    failed = next((e for e in events if e.event_type == "session_failed"), None)
    assert failed is not None
    assert failed.payload is not None
    assert failed.payload["exit_code"] is None


# --- handle() returns before the run finishes (non-blocking) ---


def test_handle_returns_before_run_completes():
    """handle() must return immediately; agent_session_started arrives before the run ends."""
    run_started = asyncio.Event()
    run_can_proceed = asyncio.Event()
    events_at_return: list[str] = []

    async def blocking_runner(command: list[str]) -> RunResult:
        run_started.set()
        await run_can_proceed.wait()
        return RunResult(returncode=0, stdout="result", stderr="")

    runner = ClaudeCodeRunner(runner=blocking_runner)
    handler = AgentCommandHandler(runner)

    async def run_test() -> None:
        events: list[RuntimeEvent] = []

        async def emit(event: RuntimeEvent) -> None:
            events.append(event)

        # handle() should return before run completes
        await handler.handle(_make_command(), emit)

        # At this point handle() has returned; the bg task has not finished
        events_at_return.extend(e.event_type for e in events)

        # Now let the run complete
        run_can_proceed.set()
        await asyncio.gather(*handler._tasks)

    asyncio.run(run_test())

    # agent_session_started was emitted synchronously before handle() returned
    assert "agent_session_started" in events_at_return
    # session_completed was NOT yet emitted when handle() returned
    assert "session_completed" not in events_at_return


# --- Unsupported command type: no events ---


def test_unsupported_command_emits_nothing():
    runner = _make_runner(ClaudeSuccess(result=""))
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    asyncio.run(
        handler.handle(
            Command(type="stop_agent_session", devcontainer_id="dc-1"),  # type: ignore[arg-type]
            emit,
        )
    )
    assert events == []
