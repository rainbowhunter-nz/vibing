"""AgentCommandHandler: dispatches Commands to ClaudeCodeRunner, emits RuntimeEvents."""

import asyncio
from collections.abc import Awaitable, Callable

from logzero import logger
from vibing_protocol import Command, CommandType, EventType, RuntimeEvent, RuntimeEventSource

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner, ClaudeFailure, ClaudeProcess

_SOURCE: RuntimeEventSource = RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT

EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


class AgentCommandHandler:
    def __init__(self, runner: ClaudeCodeRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()
        self._processes: dict[str, ClaudeProcess] = {}
        self._session_tasks: dict[str, asyncio.Task] = {}

    async def handle(self, command: Command, emit: EmitFn) -> None:
        if command.type == CommandType.START_AGENT_SESSION:
            await self._start_agent_session(command, emit)
        elif command.type == CommandType.RESUME_AGENT_SESSION:
            await self._start_agent_session(command, emit, resume=True)
        elif command.type == CommandType.STOP_AGENT_SESSION:
            await self._stop_agent_session(command, emit)
        elif command.type == CommandType.SEND_USER_INPUT:
            await self._send_user_input(command, emit)
        elif command.type == CommandType.RESOLVE_APPROVAL:
            await self._resolve_approval(command, emit)
        else:
            logger.info("Ignoring unsupported command type: %s", command.type)

    async def _start_agent_session(
        self, command: Command, emit: EmitFn, resume: bool = False
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
        session_id = command.agent_session_id or ""
        self._processes[session_id] = process
        task = asyncio.create_task(self._run_claude(command, emit, process, session_id))
        self._tasks.add(task)
        self._session_tasks[session_id] = task
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(lambda _: self._session_tasks.pop(session_id, None))

    async def _run_claude(
        self, command: Command, emit: EmitFn, process: ClaudeProcess, session_id: str
    ) -> None:
        try:
            result = await process.wait()
        except asyncio.CancelledError:
            raise  # let CancelledError propagate; stop handler emits session_stopped
        finally:
            self._processes.pop(session_id, None)

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

    async def _stop_agent_session(self, command: Command, emit: EmitFn) -> None:
        session_id = command.agent_session_id or ""
        process = self._processes.pop(session_id, None)
        task = self._session_tasks.pop(session_id, None)

        if process is not None:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            await process.terminate()

        await emit(
            RuntimeEvent(
                event_type=EventType.SESSION_STOPPED,
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                agent_session_id=command.agent_session_id,
            )
        )
