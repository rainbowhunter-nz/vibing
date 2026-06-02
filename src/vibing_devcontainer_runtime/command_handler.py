"""AgentCommandHandler: dispatches Commands to ClaudeCodeRunner, emits RuntimeEvents."""

import asyncio
from collections.abc import Awaitable, Callable

from logzero import logger
from vibing_protocol import Command, RuntimeEvent, RuntimeEventSource

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner, ClaudeFailure, ClaudeProcess

_SOURCE: RuntimeEventSource = "devcontainer_runtime_agent"

EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


class AgentCommandHandler:
    def __init__(self, runner: ClaudeCodeRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()
        self._processes: dict[str, ClaudeProcess] = {}
        self._session_tasks: dict[str, asyncio.Task] = {}

    async def handle(self, command: Command, emit: EmitFn) -> None:
        if command.type == "start_agent_session":
            await self._start_agent_session(command, emit)
        elif command.type == "stop_agent_session":
            await self._stop_agent_session(command, emit)
        elif command.type == "send_user_input":
            await self._send_user_input(command, emit)
        elif command.type == "resolve_approval":
            await self._resolve_approval(command, emit)
        else:
            logger.info("Ignoring unsupported command type: %s", command.type)

    async def _start_agent_session(self, command: Command, emit: EmitFn) -> None:
        await emit(
            RuntimeEvent(
                event_type="agent_session_started",
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                agent_session_id=command.agent_session_id,
            )
        )
        prompt = (command.payload or {}).get("prompt", "")
        process = self._runner.start(prompt)
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
            await emit(
                RuntimeEvent(
                    event_type="session_failed",
                    source=_SOURCE,
                    devcontainer_id=command.devcontainer_id,
                    agent_session_id=command.agent_session_id,
                    payload={"exit_code": result.exit_code, "stderr_tail": result.stderr_tail},
                )
            )
        else:
            await emit(
                RuntimeEvent(
                    event_type="session_completed",
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
                event_type="user_input_sent",
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
                event_type="approval_resolved",
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
                event_type="session_stopped",
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
                agent_session_id=command.agent_session_id,
            )
        )
