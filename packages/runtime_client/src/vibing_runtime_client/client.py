"""Shared runtime-channel WebSocket client: reconnect loop and command queue.

Connects to the Control Plane runtime WebSocket (ADR-0003), registers, and serially
processes the Commands it receives. Connection failures and disconnects trigger
reconnection with bounded exponential backoff. The command queue is in-memory and
per-session, so in-flight Commands are never replayed after a disconnect or process exit.

This module owns the transport; callers supply the register envelope and command handler.
"""

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import websockets
from logzero import logger
from pydantic import ValidationError
from vibing_protocol import (
    Command,
    CommandEnvelope,
    RegisterEnvelope,
    RuntimeEvent,
    RuntimeEventEnvelope,
)

EmitFn = Callable[[RuntimeEvent], Awaitable[None]]
CommandHandler = Callable[[Command, EmitFn], Awaitable[None]]
ConnectFn = Callable[[str], AbstractAsyncContextManager[Any]]
SleepFn = Callable[[float], Awaitable[None]]


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


class RuntimeChannelClient:
    """Connects to the Control Plane runtime channel and serially runs received Commands."""

    def __init__(
        self,
        control_plane_url: str,
        register: RegisterEnvelope,
        handler: CommandHandler = _noop_handler,
        *,
        connect: ConnectFn = _default_connect,
        sleep: SleepFn | None = None,
        backoff: Backoff | None = None,
    ) -> None:
        self._url = control_plane_url
        self._register = register
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
                async with self._connect(self._url) as ws:
                    self._backoff.reset()
                    await self._run_session(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Runtime channel disconnected: %s", exc)
            if self._stopped:
                break
            delay = self._backoff.next_delay()
            logger.info("Reconnecting in %.1fs", delay)
            await self._sleep(delay)

    async def _run_session(self, ws: Any) -> None:
        await ws.send(json.dumps(self._register.model_dump()))
        logger.info("Registered with control plane; awaiting commands")
        queue: asyncio.Queue[Command] = asyncio.Queue()
        consumer = asyncio.create_task(self._consume(queue, ws))
        try:
            while True:
                command = _parse_command(await ws.recv())
                if command is not None:
                    logger.info(
                        "Received command %s (devcontainer=%s)",
                        command.type,
                        command.devcontainer_id,
                    )
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
            logger.info(
                "Emitting event %s (devcontainer=%s)",
                event.event_type,
                event.devcontainer_id,
            )
            await ws.send(json.dumps(RuntimeEventEnvelope(event=event).model_dump()))

        return emit
