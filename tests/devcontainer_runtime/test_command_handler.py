"""Tests for AgentCommandHandler — fake streaming runner, no real subprocess."""

import asyncio
import json
from collections.abc import AsyncIterator

from vibing_devcontainer_runtime.claude_runner import (
    ClaudeCodeRunner,
    ClaudeSuccess,
)
from vibing_devcontainer_runtime.command_handler import AgentCommandHandler
from vibing_protocol import Command, RuntimeEvent, TurnDeltaEnvelope


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


def _result_line(result: str = "", is_error: bool = False) -> str:
    return json.dumps(
        {"type": "result", "subtype": "success", "is_error": is_error, "result": result}
    )


def _success_runner(result_text: str) -> ClaudeCodeRunner:
    async def fake(command: list[str]) -> AsyncIterator[str]:
        yield _result_line(result_text)

    return ClaudeCodeRunner(runner=fake)


def _failure_runner(stderr: str) -> ClaudeCodeRunner:
    async def fake(command: list[str]) -> AsyncIterator[str]:
        yield _result_line(is_error=True)

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
    runner = _success_runner("done")
    handler = AgentCommandHandler(runner)
    events = asyncio.run(_collect_events(handler, _make_command()))
    assert events[0].event_type == "agent_session_started"
    assert events[0].source == "devcontainer_runtime_agent"
    assert events[0].devcontainer_id == "dc-1"
    assert events[0].agent_session_id == "sess-1"


# --- session_completed on success ---


def test_start_success_emits_session_completed():
    runner = _success_runner("output text")
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
    runner = _failure_runner("boom")
    handler = AgentCommandHandler(runner)
    events = asyncio.run(_collect_events(handler, _make_command()))
    types = [e.event_type for e in events]
    assert "session_failed" in types
    failed = next(e for e in events if e.event_type == "session_failed")
    assert failed.payload is not None
    assert "exit_code" in failed.payload
    assert "stderr_tail" in failed.payload
    assert failed.agent_session_id == "sess-1"
    assert failed.devcontainer_id == "dc-1"


# --- session_failed when binary is missing ---


def test_start_missing_binary_emits_session_failed_not_crash():
    async def raising_runner(command: list[str]):
        raise FileNotFoundError("no claude")
        yield ""  # pragma: no cover

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

    async def blocking_runner(command: list[str]):
        run_started.set()
        await run_can_proceed.wait()
        yield _result_line("result")

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


# --- turn-deltas flow out via emit_delta while the run streams (ADR-0010) ---


def test_start_streams_turn_deltas_via_emit_delta():
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

    async def streaming(command: list[str]) -> AsyncIterator[str]:
        yield json.dumps({"type": "system", "subtype": "init"})
        yield _msg_start("msg_1")
        yield _text("Hel")
        yield _text("lo")
        yield _result_line("Hello")

    handler = AgentCommandHandler(ClaudeCodeRunner(runner=streaming))
    events: list[RuntimeEvent] = []
    deltas: list[TurnDeltaEnvelope] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    async def emit_delta(env: TurnDeltaEnvelope) -> None:
        deltas.append(env)

    async def run_test() -> None:
        await handler.handle(_make_command(), emit, emit_delta)
        await asyncio.gather(*handler._tasks)

    asyncio.run(run_test())

    kinds = [d.delta.kind for d in deltas]
    assert kinds == ["run_started", "text", "text", "run_ended"]
    text_deltas = [d.delta for d in deltas if d.delta.kind == "text"]
    assert [t.text for t in text_deltas] == ["Hel", "lo"]
    assert all(d.agent_session_id == "sess-1" and d.devcontainer_id == "dc-1" for d in deltas)
    # Terminal mapping still drives session_completed.
    assert "session_completed" in [e.event_type for e in events]


# --- Unsupported command type: no events ---


def test_unsupported_command_emits_nothing():
    runner = _success_runner("")
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
    runner = _success_runner("")
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
    runner = _success_runner("")
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
    runner = _success_runner("")
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
        async def wait(self, on_delta) -> ClaudeSuccess:  # type: ignore[return]
            run_started.set()
            await run_blocked.wait()
            # unreachable in this test path (task cancelled)

        async def terminate(self) -> None:
            nonlocal terminate_called
            terminate_called = True
            run_blocked.set()

    from vibing_devcontainer_runtime.claude_runner import ClaudeProcess

    class FakeRunner(ClaudeCodeRunner):
        def start(
            self, prompt: str, session_id: str | None = None, resume: bool = False
        ) -> ClaudeProcess:  # type: ignore[override]
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
        async def wait(self, on_delta) -> ClaudeSuccess:  # type: ignore[return]
            run_started.set()
            await run_blocked.wait()

        async def terminate(self) -> None:
            run_blocked.set()

    from vibing_devcontainer_runtime.claude_runner import ClaudeProcess

    class BlockingRunner(ClaudeCodeRunner):
        def start(
            self, prompt: str, session_id: str | None = None, resume: bool = False
        ) -> ClaudeProcess:  # type: ignore[override]
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

        async def wait(self, on_delta) -> ClaudeSuccess:
            return ClaudeSuccess(result="done")

        async def terminate(self) -> None:
            pass  # no-op; run already done

    class InstantRunner(ClaudeCodeRunner):
        def start(
            self, prompt: str, session_id: str | None = None, resume: bool = False
        ) -> ClaudeProcess:  # type: ignore[override]
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
        async def wait(self, on_delta) -> ClaudeSuccess:
            return ClaudeSuccess(result="done")

        async def terminate(self) -> None:
            pass

    class CapturingRunner(ClaudeCodeRunner):
        def start(
            self, prompt: str, session_id: str | None = None, resume: bool = False
        ) -> ClaudeProcess:  # type: ignore[override]
            captured_sessions.append(session_id)
            return CapturingProcess()

    handler = AgentCommandHandler(CapturingRunner())
    cmd = _make_command(agent_session_id="abc-123")
    asyncio.run(_collect_events(handler, cmd))

    assert captured_sessions == ["abc-123"]


# ============================================================
# resume_agent_session — AC1, AC3, AC4 (reuses start path with --resume)
# ============================================================


def test_resume_builds_resume_flag_and_emits_lifecycle():
    """resume_agent_session invokes the runner in RESUME mode (--resume <id>, no
    --session-id) and reuses the started → completed lifecycle (no new event types)."""
    captured: list[list[str]] = []

    async def capturing(command: list[str]) -> AsyncIterator[str]:
        captured.append(command)
        yield _result_line("resumed output")

    runner = ClaudeCodeRunner(runner=capturing)
    handler = AgentCommandHandler(runner)
    cmd = _make_command(type_="resume_agent_session", agent_session_id="abc-123")
    events = asyncio.run(_collect_events(handler, cmd))

    assert "--resume" in captured[0]
    assert captured[0][captured[0].index("--resume") + 1] == "abc-123"
    assert "--session-id" not in captured[0]

    types = [e.event_type for e in events]
    assert types[0] == "agent_session_started"
    assert "session_completed" in types


def test_resume_failure_emits_session_failed():
    runner = _failure_runner("boom")
    handler = AgentCommandHandler(runner)
    cmd = _make_command(type_="resume_agent_session", agent_session_id="abc-123")
    events = asyncio.run(_collect_events(handler, cmd))
    assert "session_failed" in [e.event_type for e in events]


# stop with no running process emits session_stopped (idempotent)


def test_stop_with_no_running_process_emits_session_stopped():
    runner = _success_runner("done")
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    asyncio.run(handler.handle(_make_stop_command(), emit))

    event_types = [e.event_type for e in events]
    assert "session_stopped" in event_types
