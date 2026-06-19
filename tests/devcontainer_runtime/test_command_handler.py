"""Tests for AgentCommandHandler — fake streaming runner, no real subprocess."""

import asyncio
import json
from collections.abc import AsyncIterator

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from vibing_devcontainer_runtime.claude_runner import (
    ClaudeCodeRunner,
    ClaudeProcess,
    ClaudeSuccess,
)
from vibing_devcontainer_runtime.command_handler import AgentCommandHandler
from vibing_protocol import Command, RuntimeEvent, RuntimeEventEnvelope, TurnDeltaEnvelope

from .fakes import scripted_runner


def _sender(
    events: list[RuntimeEvent], deltas: list[TurnDeltaEnvelope] | None = None
) -> Callable[[BaseModel], Awaitable[None]]:
    """Collect sent envelopes: RuntimeEvents unwrapped into `events`, deltas into `deltas`."""

    async def send(envelope: BaseModel) -> None:
        if isinstance(envelope, RuntimeEventEnvelope):
            events.append(envelope.event)
        elif deltas is not None and isinstance(envelope, TurnDeltaEnvelope):
            deltas.append(envelope)

    return send


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

    return scripted_runner(fake)


def _failure_runner() -> ClaudeCodeRunner:
    async def fake(command: list[str]) -> AsyncIterator[str]:
        yield _result_line(is_error=True)

    return scripted_runner(fake)


def _process_runner(process: ClaudeProcess) -> ClaudeCodeRunner:
    """Inject a fake ClaudeProcess at the one seam, regardless of the command."""
    return ClaudeCodeRunner(process_factory=lambda command: process)


async def _collect_events(handler: AgentCommandHandler, command: Command) -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []

    send = _sender(events)

    await handler.handle(command, send)
    # Allow background tasks to complete
    await handler.wait_for_idle()
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
    runner = _failure_runner()
    handler = AgentCommandHandler(runner)
    events = asyncio.run(_collect_events(handler, _make_command()))
    types = [e.event_type for e in events]
    assert "session_failed" in types
    failed = next(e for e in events if e.event_type == "session_failed")
    # is_error result with a clean exit -> exit_code 0, no stderr captured.
    assert failed.payload == {"exit_code": 0, "stderr_tail": ""}
    assert failed.agent_session_id == "sess-1"
    assert failed.devcontainer_id == "dc-1"


# --- session_failed when binary is missing ---


def test_start_missing_binary_emits_session_failed_not_crash():
    async def raising_runner(command: list[str]):
        raise FileNotFoundError("no claude")
        yield ""  # pragma: no cover

    runner = scripted_runner(raising_runner)
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

    runner = scripted_runner(blocking_runner)
    handler = AgentCommandHandler(runner)

    async def run_test() -> None:
        events: list[RuntimeEvent] = []
        send = _sender(events)

        # handle() should return before run completes
        await handler.handle(_make_command(), send)

        # At this point handle() has returned; the bg task has not finished
        events_at_return.extend(e.event_type for e in events)

        # Now let the run complete
        run_can_proceed.set()
        await handler.wait_for_idle()

    asyncio.run(run_test())

    # agent_session_started was emitted synchronously before handle() returned
    assert "agent_session_started" in events_at_return
    # session_completed was NOT yet emitted when handle() returned
    assert "session_completed" not in events_at_return


# --- turn-deltas flow out over send while the run streams (ADR-0010) ---


def test_start_streams_turn_deltas_over_send():
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

    handler = AgentCommandHandler(scripted_runner(streaming))
    events: list[RuntimeEvent] = []
    deltas: list[TurnDeltaEnvelope] = []

    send = _sender(events, deltas)

    async def run_test() -> None:
        await handler.handle(_make_command(), send)
        await handler.wait_for_idle()

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

    send = _sender(events)

    asyncio.run(
        handler.handle(
            Command(type="start_devcontainer", devcontainer_id="dc-1"),  # type: ignore[arg-type]
            send,
        )
    )
    assert events == []


# --- resolve_approval: emits approval_resolved ---


def test_resolve_approval_emits_approval_resolved():
    runner = _success_runner("")
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    send = _sender(events)

    asyncio.run(
        handler.handle(
            Command(
                type="resolve_approval",  # type: ignore[arg-type]
                devcontainer_id="dc-1",
                agent_session_id="sess-1",
                payload={"approval_request_id": "ar-abc", "resolution": "approved"},
            ),
            send,
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

    send = _sender(events)

    asyncio.run(
        handler.handle(
            Command(
                type="resolve_approval",  # type: ignore[arg-type]
                devcontainer_id="dc-1",
                agent_session_id="sess-1",
                payload={"approval_request_id": "ar-xyz", "resolution": "rejected"},
            ),
            send,
        )
    )
    assert len(events) == 1
    assert events[0].payload == {"approval_request_id": "ar-xyz", "resolution": "rejected"}


# --- send_user_input: emits user_input_sent ---


def test_send_user_input_emits_user_input_sent():
    runner = _success_runner("")
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    send = _sender(events)

    asyncio.run(
        handler.handle(
            Command(
                type="send_user_input",
                devcontainer_id="dc-1",
                agent_session_id="sess-1",
                payload={"inbox_event_id": "inbox-abc", "text": "my answer"},
            ),
            send,
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

    class FakeProcess(ClaudeProcess):
        async def wait(self, on_delta) -> ClaudeSuccess:  # type: ignore[return]
            run_started.set()
            await run_blocked.wait()
            # unreachable in this test path (task cancelled)

        async def terminate(self) -> None:
            nonlocal terminate_called
            terminate_called = True
            run_blocked.set()

    handler = AgentCommandHandler(_process_runner(FakeProcess()))
    events: list[RuntimeEvent] = []

    send = _sender(events)

    async def run_test() -> None:
        start_cmd = _make_command()
        await handler.handle(start_cmd, send)
        await run_started.wait()  # ensure run is in-flight

        stop_cmd = _make_stop_command()
        await handler.handle(stop_cmd, send)

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

    class BlockingProcess(ClaudeProcess):
        async def wait(self, on_delta) -> ClaudeSuccess:  # type: ignore[return]
            run_started.set()
            await run_blocked.wait()

        async def terminate(self) -> None:
            run_blocked.set()

    handler = AgentCommandHandler(_process_runner(BlockingProcess()))
    events: list[RuntimeEvent] = []

    send = _sender(events)

    async def run_test() -> None:
        nonlocal stop_returned_before_run_finished
        await handler.handle(_make_command(), send)
        await run_started.wait()

        # handle(stop) should return before the run finishes
        await handler.handle(_make_stop_command(), send)
        # If we reach here, handle returned; run is still blocked by run_blocked
        # (terminate sets run_blocked, but the bg task may already be cancelled)
        stop_returned_before_run_finished = True

        # Let any remaining tasks finish
        await handler.wait_for_idle()

    asyncio.run(run_test())

    assert stop_returned_before_run_finished
    event_types = [e.event_type for e in events]
    assert "session_stopped" in event_types


# AC4: race — at least one terminal event (not suppression)


def test_stop_after_natural_completion_emits_both_terminals_not_suppressed():
    """A run that completes before stop arrives still emits session_completed; the
    later stop is a no-op on the finished run but still emits session_stopped."""
    terminate_calls = 0

    class InstantProcess(ClaudeProcess):
        """Completes immediately — the run finishes before stop is handled."""

        async def wait(self, on_delta) -> ClaudeSuccess:
            return ClaudeSuccess(result="done")

        async def terminate(self) -> None:
            nonlocal terminate_calls
            terminate_calls += 1

    handler = AgentCommandHandler(_process_runner(InstantProcess()))
    events: list[RuntimeEvent] = []

    send = _sender(events)

    async def run_test() -> None:
        await handler.handle(_make_command(), send)
        # Let bg task complete naturally first
        await handler.wait_for_idle()
        # Now send stop — session already done
        await handler.handle(_make_stop_command(), send)

    asyncio.run(run_test())

    assert [e.event_type for e in events] == [
        "agent_session_started",
        "session_completed",
        "session_stopped",
    ]
    # A finished run is never terminated again.
    assert terminate_calls == 0


# --- session_id passed to runner ---


def test_start_agent_session_passes_session_id_to_runner():
    """The command's session id reaches the runner (built into --session-id)."""
    captured: list[list[str]] = []

    async def capturing(command: list[str]) -> AsyncIterator[str]:
        captured.append(command)
        yield _result_line("done")

    handler = AgentCommandHandler(scripted_runner(capturing))
    cmd = _make_command(agent_session_id="abc-123")
    asyncio.run(_collect_events(handler, cmd))

    assert "--session-id" in captured[0]
    assert captured[0][captured[0].index("--session-id") + 1] == "abc-123"


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

    runner = scripted_runner(capturing)
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
    runner = _failure_runner()
    handler = AgentCommandHandler(runner)
    cmd = _make_command(type_="resume_agent_session", agent_session_id="abc-123")
    events = asyncio.run(_collect_events(handler, cmd))
    assert "session_failed" in [e.event_type for e in events]


# stop with no running process emits session_stopped (idempotent)


def test_stop_with_no_running_process_emits_session_stopped():
    runner = _success_runner("done")
    handler = AgentCommandHandler(runner)
    events: list[RuntimeEvent] = []

    send = _sender(events)

    asyncio.run(handler.handle(_make_stop_command(), send))

    event_types = [e.event_type for e in events]
    assert "session_stopped" in event_types
