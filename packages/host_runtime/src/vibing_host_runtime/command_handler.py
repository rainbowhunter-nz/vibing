"""Command handler: wires received Commands to DevcontainerCliAdapter, emits RuntimeEvents."""

import dataclasses
from collections.abc import Awaitable, Callable
from typing import Protocol

from logzero import logger
from vibing_protocol import Command, RuntimeEvent

from vibing_host_runtime.devcontainer_cli import DevcontainerCliAdapter, DevcontainerFailure

_SOURCE = "host_runtime_worker"

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
        if command.type == "start_devcontainer":
            await self._dispatch(
                command,
                emit,
                "start",
                "devcontainer_starting",
                "devcontainer_started",
                self._adapter.start,
            )
        elif command.type == "stop_devcontainer":
            await self._dispatch(
                command,
                emit,
                "stop",
                "devcontainer_stopping",
                "devcontainer_stopped",
                self._adapter.stop,
            )
        else:
            logger.info("Ignoring unsupported command type: %s", command.type)

    async def _dispatch(
        self,
        command: Command,
        emit: EmitFn,
        operation: str,
        pre_event: str,
        success_event: str,
        adapter_method: Callable[[str], Awaitable],
    ) -> None:
        local_path = (command.payload or {}).get("local_path")
        if not local_path:
            if command.devcontainer_id:
                await emit(
                    RuntimeEvent(
                        event_type="devcontainer_failed",
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
                event_type=pre_event,  # type: ignore[arg-type]
                source=_SOURCE,
                devcontainer_id=command.devcontainer_id,
            )
        )
        result = await adapter_method(local_path)
        if isinstance(result, DevcontainerFailure):
            await emit(
                RuntimeEvent(
                    event_type="devcontainer_failed",
                    source=_SOURCE,
                    devcontainer_id=command.devcontainer_id,
                    payload=dataclasses.asdict(result),
                )
            )
        else:
            payload = result.payload if operation == "start" else None
            await emit(
                RuntimeEvent(
                    event_type=success_event,  # type: ignore[arg-type]
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
