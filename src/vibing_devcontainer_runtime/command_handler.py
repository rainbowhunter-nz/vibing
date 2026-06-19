"""AgentCommandHandler: dispatches Commands to ClaudeCodeRunner, sends RuntimeEvents.

While a session runs, normalized turn-deltas (ADR-0010) flow out over the same `send`
as RuntimeEvents — the handler picks the envelope. The terminal `result` event still
drives the session_completed/session_failed mapping; deltas are ephemeral and never
persisted.
"""

import asyncio
from collections.abc import Awaitable, Callable

from logzero import logger
from pydantic import BaseModel
from vibing_protocol import (
    Command,
    CommandType,
    EventType,
    RuntimeEvent,
    RuntimeEventEnvelope,
    RuntimeEventSource,
    TurnDelta,
    TurnDeltaEnvelope,
)

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner, ClaudeFailure, ClaudeProcess
from vibing_devcontainer_runtime.harness_manager import HarnessManager
from vibing_devcontainer_runtime.running_sessions import RunningSessions

_SOURCE: RuntimeEventSource = RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT

SendFn = Callable[[BaseModel], Awaitable[None]]
EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


def _make_emit(send: SendFn) -> EmitFn:
    async def emit(event: RuntimeEvent) -> None:
        logger.info(
            "Emitting event %s (devcontainer=%s, session=%s)",
            event.event_type,
            event.devcontainer_id,
            event.agent_session_id,
        )
        await send(RuntimeEventEnvelope(event=event))

    return emit


class AgentCommandHandler:
    def __init__(
        self, runner: ClaudeCodeRunner, harness_manager: HarnessManager | None = None
    ) -> None:
        self._runner = runner
        self._sessions = RunningSessions()
        self._harness_manager = harness_manager

    async def wait_for_idle(self) -> None:
        """Await every in-flight run to settle (shutdown / tests)."""
        await self._sessions.drain()

    async def handle(self, command: Command, send: SendFn) -> None:
        emit = _make_emit(send)
        if command.type == CommandType.START_AGENT_SESSION:
            await self._start_agent_session(command, emit, send)
        elif command.type == CommandType.RESUME_AGENT_SESSION:
            await self._start_agent_session(command, emit, send, resume=True)
        elif command.type == CommandType.STOP_AGENT_SESSION:
            await self._stop_agent_session(command, emit)
        elif command.type == CommandType.SEND_USER_INPUT:
            await self._send_user_input(command, emit)
        elif command.type == CommandType.RESOLVE_APPROVAL:
            await self._resolve_approval(command, emit)
        elif command.type == CommandType.AUTHENTICATE_HARNESS:
            await self._authenticate_harness(command, emit)
        else:
            logger.info("Ignoring unsupported command type: %s", command.type)

    async def _start_agent_session(
        self, command: Command, emit: EmitFn, send: SendFn, resume: bool = False
    ) -> None:
        prompt = (command.payload or {}).get("prompt", "")
        logger.info(
            "Handling %s (devcontainer=%s, session=%s, prompt_len=%d, prompt=%r)",
            "resume_agent_session" if resume else "start_agent_session",
            command.devcontainer_id,
            command.agent_session_id,
            len(prompt),
            prompt[:200] + ("..." if len(prompt) > 200 else ""),
        )
        await emit(
            RuntimeEvent(
                event_type=EventType.AGENT_SESSION_STARTED,
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                agent_session_id=command.agent_session_id,
            )
        )
        process = self._runner.start(prompt, session_id=command.agent_session_id, resume=resume)
        logger.info(
            "Spawned claude background task (devcontainer=%s, session=%s)",
            command.devcontainer_id,
            command.agent_session_id,
        )
        task = asyncio.create_task(self._run_claude(command, emit, send, process))
        self._sessions.track(command.agent_session_id or "", process, task)

    async def _run_claude(
        self,
        command: Command,
        emit: EmitFn,
        send: SendFn,
        process: ClaudeProcess,
    ) -> None:
        async def on_delta(delta: TurnDelta) -> None:
            await send(
                TurnDeltaEnvelope(
                    devcontainer_id=command.devcontainer_id or "",
                    agent_session_id=command.agent_session_id or "",
                    delta=delta,
                )
            )

        try:
            result = await process.wait(on_delta)
        except asyncio.CancelledError:
            raise  # let CancelledError propagate; stop handler emits session_stopped

        if isinstance(result, ClaudeFailure):
            logger.warning(
                "Session failed (devcontainer=%s, session=%s, exit_code=%s, message=%s, stderr=%s)",
                command.devcontainer_id,
                command.agent_session_id,
                result.exit_code,
                result.message,
                result.stderr_tail[:500] + ("..." if len(result.stderr_tail) > 500 else ""),
            )
            await emit(
                RuntimeEvent(
                    event_type=EventType.SESSION_FAILED,
                    source=_SOURCE,
                    devcontainer_id=command.devcontainer_id,
                    agent_session_id=command.agent_session_id,
                    payload={"exit_code": result.exit_code, "stderr_tail": result.stderr_tail},
                )
            )
        else:
            preview = result.result[:500] + ("..." if len(result.result) > 500 else "")
            logger.info(
                "Session completed (devcontainer=%s, session=%s, result_len=%d, result=%s)",
                command.devcontainer_id,
                command.agent_session_id,
                len(result.result),
                preview,
            )
            await emit(
                RuntimeEvent(
                    event_type=EventType.SESSION_COMPLETED,
                    source=_SOURCE,
                    devcontainer_id=command.devcontainer_id,
                    agent_session_id=command.agent_session_id,
                    payload={"result": result.result},
                )
            )

    async def _send_user_input(self, command: Command, emit: EmitFn) -> None:
        payload = command.payload or {}
        await emit(
            RuntimeEvent(
                event_type=EventType.USER_INPUT_SENT,
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                agent_session_id=command.agent_session_id,
                payload={"inbox_event_id": payload.get("inbox_event_id")},
            )
        )

    async def _resolve_approval(self, command: Command, emit: EmitFn) -> None:
        payload = command.payload or {}
        await emit(
            RuntimeEvent(
                event_type=EventType.APPROVAL_RESOLVED,
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                agent_session_id=command.agent_session_id,
                payload={
                    "approval_request_id": payload.get("approval_request_id"),
                    "resolution": payload.get("resolution"),
                },
            )
        )

    async def _authenticate_harness(self, command: Command, emit: EmitFn) -> None:
        if self._harness_manager is None:
            logger.info("authenticate_harness received but no harness manager wired")
            return
        payload = command.payload or {}
        harness = payload.get("harness", "")
        status = await self._harness_manager.authenticate(harness, payload.get("credentials") or {})
        await emit(
            RuntimeEvent(
                event_type=EventType.HARNESS_STATUS,
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                payload={
                    "harness": status.name,
                    "installed": status.installed,
                    "authenticated": status.authenticated,
                },
            )
        )

    async def _stop_agent_session(self, command: Command, emit: EmitFn) -> None:
        await self._sessions.stop(command.agent_session_id or "")
        await emit(
            RuntimeEvent(
                event_type=EventType.SESSION_STOPPED,
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                agent_session_id=command.agent_session_id,
            )
        )
