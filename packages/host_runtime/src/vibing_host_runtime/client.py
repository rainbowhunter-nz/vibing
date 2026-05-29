"""Host Runtime Worker process: runtime-channel client, reconnect loop, command queue.

A separately-started process (ADR-0003) that connects to the Control Plane runtime
WebSocket, registers, and serially processes the Commands it receives. Connection
failures and disconnects trigger reconnection with bounded exponential backoff. The
command queue is in-memory and per-session, so in-flight Commands are never replayed
after a disconnect or process exit.

Command execution is wired to the Dev Container CLI adapter via `DevcontainerCommandHandler`;
this module owns the process, transport, and queue.
"""

import argparse
import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

import websockets
from pydantic import ValidationError
from vibing_protocol import (
    Command,
    CommandEnvelope,
    RegisterEnvelope,
    RuntimeEvent,
    RuntimeEventEnvelope,
)

logger = logging.getLogger(__name__)

DEFAULT_CONTROL_PLANE_URL = "ws://127.0.0.1:8000/api/v1/runtime/ws"
DEFAULT_DEVCONTAINER_CLI = "devcontainer"

EmitFn = Callable[[RuntimeEvent], Awaitable[None]]
CommandHandler = Callable[[Command, EmitFn], Awaitable[None]]
ConnectFn = Callable[[str], AbstractAsyncContextManager[Any]]
SleepFn = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class WorkerConfig:
    control_plane_url: str
    devcontainer_cli: str


def parse_args(argv: list[str] | None = None) -> WorkerConfig:
    parser = argparse.ArgumentParser(
        prog="vibing-host-runtime",
        description="Host Runtime Worker: drives Devcontainer lifecycle for the Control Plane.",
    )
    parser.add_argument(
        "--control-plane-url",
        default=DEFAULT_CONTROL_PLANE_URL,
        help="Control Plane runtime WebSocket URL",
    )
    parser.add_argument(
        "--devcontainer-cli",
        default=DEFAULT_DEVCONTAINER_CLI,
        help="Dev Container CLI binary name or path",
    )
    namespace = parser.parse_args(argv)
    return WorkerConfig(
        control_plane_url=namespace.control_plane_url,
        devcontainer_cli=namespace.devcontainer_cli,
    )


class Backoff:
    """Bounded exponential backoff: initial, then *factor each step, capped at maximum."""

    def __init__(self, initial: float = 0.5, factor: float = 2.0, maximum: float = 30.0) -> None:
        self._initial = initial
        self._factor = factor
        self._maximum = maximum
        self._current = initial

    def reset(self) -> None:
        self._current = self._initial

    def next_delay(self) -> float:
        delay = min(self._current, self._maximum)
        self._current = min(self._current * self._factor, self._maximum)
        return delay


async def _noop_handler(command: Command, emit: EmitFn) -> None:
    logger.info("Received command %s; no command handler wired yet", command.type)


def _default_connect(url: str) -> AbstractAsyncContextManager[Any]:
    return websockets.connect(url)


def _parse_command(raw: str) -> Command | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(message, dict) or message.get("type") != "command":
        return None
    try:
        return CommandEnvelope.model_validate(message).command
    except ValidationError:
        return None


class HostRuntimeClient:
    """Connects to the Control Plane runtime channel and serially runs received Commands."""

    def __init__(
        self,
        config: WorkerConfig,
        *,
        handler: CommandHandler = _noop_handler,
        connect: ConnectFn = _default_connect,
        sleep: SleepFn | None = None,
        backoff: Backoff | None = None,
    ) -> None:
        self._config = config
        self._handler = handler
        self._connect = connect
        self._sleep: SleepFn = sleep or asyncio.sleep
        self._backoff = backoff or Backoff()
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def run(self) -> None:
        """Reconnect forever (until stopped), backing off between attempts."""
        while not self._stopped:
            try:
                async with self._connect(self._config.control_plane_url) as ws:
                    self._backoff.reset()
                    await self._run_session(ws)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Runtime channel error; reconnecting", exc_info=True)
            if self._stopped:
                break
            await self._sleep(self._backoff.next_delay())

    async def _run_session(self, ws: Any) -> None:
        await ws.send(json.dumps(RegisterEnvelope().model_dump()))
        queue: asyncio.Queue[Command] = asyncio.Queue()
        consumer = asyncio.create_task(self._consume(queue, ws))
        try:
            while True:
                command = _parse_command(await ws.recv())
                if command is not None:
                    queue.put_nowait(command)
        finally:
            consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer

    async def _consume(self, queue: "asyncio.Queue[Command]", ws: Any) -> None:
        emit = self._make_emit(ws)
        while True:
            command = await queue.get()
            try:
                await self._handler(command, emit)
            finally:
                queue.task_done()

    def _make_emit(self, ws: Any) -> EmitFn:
        async def emit(event: RuntimeEvent) -> None:
            await ws.send(json.dumps(RuntimeEventEnvelope(event=event).model_dump()))

        return emit


def main(argv: list[str] | None = None) -> None:
    from vibing_host_runtime.command_handler import DevcontainerCommandHandler
    from vibing_host_runtime.devcontainer_cli import DevcontainerCliAdapter

    logging.basicConfig(level=logging.INFO)
    config = parse_args(argv)
    adapter = DevcontainerCliAdapter(config.devcontainer_cli)
    handler = DevcontainerCommandHandler(adapter)
    client = HostRuntimeClient(config, handler=handler.handle)
    asyncio.run(client.run())
