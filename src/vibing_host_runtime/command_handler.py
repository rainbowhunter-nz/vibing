"""Command handler: wires received Commands to DevcontainerCliAdapter, emits RuntimeEvents."""

import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from logzero import logger
from vibing_protocol import Command, CommandType, EventType, RuntimeEvent, RuntimeEventSource

from vibing_host_runtime.devcontainer_cli import DevcontainerCliAdapter, DevcontainerFailure

_SOURCE: RuntimeEventSource = RuntimeEventSource.HOST_RUNTIME_WORKER

EmitFn = Callable[[RuntimeEvent], Awaitable[None]]


class _LauncherProtocol(Protocol):
    async def launch(self, devcontainer_id: str, local_path: str) -> None: ...


class DevcontainerCommandHandler:
    def __init__(
        self, adapter: DevcontainerCliAdapter, launcher: _LauncherProtocol | None = None
    ) -> None:
        self._adapter = adapter
        self._launcher = launcher

    async def handle(self, command: Command, emit: EmitFn) -> None:
        if command.type == CommandType.START_DEVCONTAINER:
            await self._dispatch(
                command,
                emit,
                "start",
                EventType.DEVCONTAINER_STARTING,
                EventType.DEVCONTAINER_STARTED,
                self._adapter.start,
            )
        elif command.type == CommandType.STOP_DEVCONTAINER:
            await self._dispatch(
                command,
                emit,
                "stop",
                EventType.DEVCONTAINER_STOPPING,
                EventType.DEVCONTAINER_STOPPED,
                self._adapter.stop,
            )
        else:
            logger.info("Ignoring unsupported command type: %s", command.type)

    async def _dispatch(
        self,
        command: Command,
        emit: EmitFn,
        operation: str,
        pre_event: EventType,
        success_event: EventType,
        adapter_method: Callable[[str], Awaitable[Any]],
    ) -> None:
        local_path = (command.payload or {}).get("local_path")
        if not local_path:
            if command.devcontainer_id:
                await emit(
                    RuntimeEvent(
                        event_type=EventType.DEVCONTAINER_FAILED,
                        source=_SOURCE,
                        devcontainer_id=command.devcontainer_id,
                        payload={"operation": operation, "message": "missing local_path"},
                    )
                )
            else:
                logger.info(
                    "Command %s missing local_path and devcontainer_id; skipping", command.type
                )
            return

        await emit(
            RuntimeEvent(
                event_type=pre_event,
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
            )
        )
        result = await adapter_method(local_path)
        if isinstance(result, DevcontainerFailure):
            logger.error(
                "devcontainer %s failed (devcontainer=%s, exit_code=%s): %s\n"
                "  command: %s\n  stderr:\n%s",
                operation,
                command.devcontainer_id,
                result.exit_code,
                result.message,
                " ".join(result.command),
                result.stderr_tail or "(empty)",
            )
            await emit(
                RuntimeEvent(
                    event_type=EventType.DEVCONTAINER_FAILED,
                    source=_SOURCE,
                    devcontainer_id=command.devcontainer_id,
                    payload=dataclasses.asdict(result),
                )
            )
        else:
            payload = result.payload if operation == "start" else None
            await emit(
                RuntimeEvent(
                    event_type=success_event,
                    source=_SOURCE,
                    devcontainer_id=command.devcontainer_id,
                    payload=payload or None,
                )
            )
            if operation == "start" and self._launcher and command.devcontainer_id and local_path:
                try:
                    await self._launcher.launch(command.devcontainer_id, local_path)
                except Exception:
                    logger.warning("Unexpected error during agent launch; ignoring")
