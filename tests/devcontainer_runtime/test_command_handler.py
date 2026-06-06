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
            Command(type="start_devcontainer", devcontainer_id="dc-1"),  # type: ignore[arg-type]
            emit,
        )
    )
    assert events == []


# --- resolve_approval: emits approval_resolved ---


def test_resolve_approval_emits_approval_resolved():
    runner = _make_runner(ClaudeSuccess(result=""))
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    asyncio.run(
        handler.handle(
            Command(
                type="resolve_approval",  # type: ignore[arg-type]
                devcontainer_id="dc-1",
                agent_session_id="sess-1",
                payload={"approval_request_id": "ar-abc", "resolution": "approved"},
            ),
            emit,
        )
    )
    assert len(events) == 1
    evt = events[0]
    assert evt.event_type == "approval_resolved"
    assert evt.source == "devcontainer_runtime_agent"
    assert evt.devcontainer_id == "dc-1"
    assert evt.agent_session_id == "sess-1"
    assert evt.payload == {"approval_request_id": "ar-abc", "resolution": "approved"}


def test_resolve_approval_rejected_emits_approval_resolved():
    runner = _make_runner(ClaudeSuccess(result=""))
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    asyncio.run(
        handler.handle(
            Command(
                type="resolve_approval",  # type: ignore[arg-type]
                devcontainer_id="dc-1",
                agent_session_id="sess-1",
                payload={"approval_request_id": "ar-xyz", "resolution": "rejected"},
            ),
            emit,
        )
    )
    assert len(events) == 1
    assert events[0].payload == {"approval_request_id": "ar-xyz", "resolution": "rejected"}


# --- send_user_input: emits user_input_sent ---


def test_send_user_input_emits_user_input_sent():
    runner = _make_runner(ClaudeSuccess(result=""))
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    asyncio.run(
        handler.handle(
            Command(
                type="send_user_input",
                devcontainer_id="dc-1",
                agent_session_id="sess-1",
                payload={"inbox_event_id": "inbox-abc", "text": "my answer"},
            ),
            emit,
        )
    )
    assert len(events) == 1
    evt = events[0]
    assert evt.event_type == "user_input_sent"
    assert evt.source == "devcontainer_runtime_agent"
    assert evt.devcontainer_id == "dc-1"
    assert evt.agent_session_id == "sess-1"
    assert evt.payload == {"inbox_event_id": "inbox-abc"}


# ============================================================
# stop_agent_session — AC2, AC3, AC4, AC5
# ============================================================


def _make_stop_command(
    devcontainer_id: str = "dc-1",
    agent_session_id: str = "sess-1",
) -> Command:
    return Command(
        type="stop_agent_session",  # type: ignore[arg-type]
        devcontainer_id=devcontainer_id,
        agent_session_id=agent_session_id,
    )


# AC2: stop terminates process and emits session_stopped


def test_stop_terminates_process_and_emits_session_stopped():
    """stop_agent_session → terminate() called on in-flight process → session_stopped emitted."""
    terminate_called = False
    run_started = asyncio.Event()
    run_blocked = asyncio.Event()

    class FakeProcess:
        async def wait(self) -> ClaudeSuccess:  # type: ignore[return]
            run_started.set()
            await run_blocked.wait()
            # unreachable in this test path (task cancelled)

        async def terminate(self) -> None:
            nonlocal terminate_called
            terminate_called = True
            run_blocked.set()

    from vibing_devcontainer_runtime.claude_runner import ClaudeProcess

    class FakeRunner(ClaudeCodeRunner):
        def start(self, prompt: str, session_id: str | None = None) -> ClaudeProcess:  # type: ignore[override]
            return FakeProcess()  # type: ignore[return-value]

    handler = AgentCommandHandler(FakeRunner())
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    async def run_test() -> None:
        start_cmd = _make_command()
        await handler.handle(start_cmd, emit)
        await run_started.wait()  # ensure run is in-flight

        stop_cmd = _make_stop_command()
        await handler.handle(stop_cmd, emit)

    asyncio.run(run_test())

    assert terminate_called
    event_types = [e.event_type for e in events]
    assert "session_stopped" in event_types
    stopped = next(e for e in events if e.event_type == "session_stopped")
    assert stopped.devcontainer_id == "dc-1"
    assert stopped.agent_session_id == "sess-1"


# AC3 + AC5: stop_agent_session processed while run is in flight (consumer not blocked)


def test_stop_handle_returns_promptly_while_run_in_flight():
    """handle(stop) returns promptly even when a run is blocking."""
    run_started = asyncio.Event()
    run_blocked = asyncio.Event()
    stop_returned_before_run_finished = False

    class BlockingProcess:
        async def wait(self) -> ClaudeSuccess:  # type: ignore[return]
            run_started.set()
            await run_blocked.wait()

        async def terminate(self) -> None:
            run_blocked.set()

    from vibing_devcontainer_runtime.claude_runner import ClaudeProcess

    class BlockingRunner(ClaudeCodeRunner):
        def start(self, prompt: str, session_id: str | None = None) -> ClaudeProcess:  # type: ignore[override]
            return BlockingProcess()  # type: ignore[return-value]

    handler = AgentCommandHandler(BlockingRunner())
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    async def run_test() -> None:
        nonlocal stop_returned_before_run_finished
        await handler.handle(_make_command(), emit)
        await run_started.wait()

        # handle(stop) should return before the run finishes
        await handler.handle(_make_stop_command(), emit)
        # If we reach here, handle returned; run is still blocked by run_blocked
        # (terminate sets run_blocked, but the bg task may already be cancelled)
        stop_returned_before_run_finished = True

        # Let any remaining tasks finish
        await asyncio.gather(*handler._tasks, return_exceptions=True)

    asyncio.run(run_test())

    assert stop_returned_before_run_finished
    event_types = [e.event_type for e in events]
    assert "session_stopped" in event_types


# AC4: race — at least one terminal event (not suppression)


def test_stop_race_yields_at_least_one_terminal_event():
    """When stop races natural completion, at least one terminal event is emitted."""
    from vibing_devcontainer_runtime.claude_runner import ClaudeProcess

    class InstantProcess:
        """Completes immediately (before stop can cancel it — simulates race)."""

        async def wait(self) -> ClaudeSuccess:
            return ClaudeSuccess(result="done")

        async def terminate(self) -> None:
            pass  # no-op; run already done

    class InstantRunner(ClaudeCodeRunner):
        def start(self, prompt: str, session_id: str | None = None) -> ClaudeProcess:  # type: ignore[override]
            return InstantProcess()  # type: ignore[return-value]

    handler = AgentCommandHandler(InstantRunner())
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    async def run_test() -> None:
        await handler.handle(_make_command(), emit)
        # Let bg task complete naturally first
        await asyncio.gather(*handler._tasks, return_exceptions=True)
        # Now send stop — session already done
        await handler.handle(_make_stop_command(), emit)

    asyncio.run(run_test())

    terminal_types = {"session_completed", "session_failed", "session_stopped"}
    emitted_terminals = [e.event_type for e in events if e.event_type in terminal_types]
    assert len(emitted_terminals) >= 1


# --- session_id passed to runner ---


def test_start_agent_session_passes_session_id_to_runner():
    """Runner must be invoked with the session id from the command."""
    captured_sessions: list[str | None] = []

    from vibing_devcontainer_runtime.claude_runner import ClaudeProcess

    class CapturingProcess(ClaudeProcess):
        async def wait(self) -> ClaudeSuccess:
            return ClaudeSuccess(result="done")

        async def terminate(self) -> None:
            pass

    class CapturingRunner(ClaudeCodeRunner):
        def start(self, prompt: str, session_id: str | None = None) -> ClaudeProcess:  # type: ignore[override]
            captured_sessions.append(session_id)
            return CapturingProcess()

    handler = AgentCommandHandler(CapturingRunner())
    cmd = _make_command(agent_session_id="abc-123")
    asyncio.run(_collect_events(handler, cmd))

    assert captured_sessions == ["abc-123"]


# stop with no running process emits session_stopped (idempotent)


def test_stop_with_no_running_process_emits_session_stopped():
    runner = _make_runner(ClaudeSuccess(result="done"))
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    asyncio.run(handler.handle(_make_stop_command(), emit))

    event_types = [e.event_type for e in events]
    assert "session_stopped" in event_types
