"""AgentCommandHandler: dispatches Commands to ClaudeCodeRunner, emits RuntimeEvents."""

import asyncio
from collections.abc import Awaitable, Callable

from logzero import logger
from vibing_protocol import Command, RuntimeEvent

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner, ClaudeFailure

_SOURCE = "devcontainer_runtime_agent"

EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


class AgentCommandHandler:
    def __init__(self, runner: ClaudeCodeRunner) -> None:
        self._runner = runner
        self._tasks: set[asyncio.Task] = set()

    async def handle(self, command: Command, emit: EmitFn) -> None:
        if command.type == "start_agent_session":
            await self._start_agent_session(command, emit)
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
        task = asyncio.create_task(self._run_claude(command, emit, prompt))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_claude(self, command: Command, emit: EmitFn, prompt: str) -> None:
        result = await self._runner.run(prompt)
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
