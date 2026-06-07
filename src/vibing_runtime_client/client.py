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
    TranscriptRequestEnvelope,
    TranscriptResponseEnvelope,
    TranscriptTurn,
    TurnDeltaEnvelope,
)

EmitFn = Callable[[RuntimeEvent], Awaitable[None]]
EmitDeltaFn = Callable[[TurnDeltaEnvelope], Awaitable[None]]
# Handlers receive emit (RuntimeEvents) and emit_delta (live turn-deltas, ADR-0010).
CommandHandler = Callable[[Command, EmitFn, EmitDeltaFn], Awaitable[None]]
TranscriptHandler = Callable[[str], Awaitable[list[TranscriptTurn]]]
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


async def _noop_handler(command: Command, emit: EmitFn, emit_delta: EmitDeltaFn) -> None:
    logger.info("Received command %s; no command handler wired yet", command.type)


async def _noop_transcript_handler(agent_session_id: str) -> list[TranscriptTurn]:
    return []


def _default_connect(url: str) -> AbstractAsyncContextManager[Any]:
    return websockets.connect(url)


def _parse_inbound(raw: str) -> Command | TranscriptRequestEnvelope | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(message, dict):
        return None
    msg_type = message.get("type")
    try:
        if msg_type == "command":
            return CommandEnvelope.model_validate(message).command
        if msg_type == "transcript_request":
            return TranscriptRequestEnvelope.model_validate(message)
    except ValidationError:
        return None
    return None


class RuntimeChannelClient:
    """Connects to the Control Plane runtime channel and serially runs received Commands."""

    def __init__(
        self,
        control_plane_url: str,
        register: RegisterEnvelope,
        handler: CommandHandler = _noop_handler,
        *,
        transcript_handler: TranscriptHandler = _noop_transcript_handler,
        connect: ConnectFn = _default_connect,
        sleep: SleepFn | None = None,
        backoff: Backoff | None = None,
    ) -> None:
        self._url = control_plane_url
        self._register = register
        self._handler = handler
        self._transcript_handler = transcript_handler
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
                inbound = _parse_inbound(await ws.recv())
                if isinstance(inbound, TranscriptRequestEnvelope):
                    await self._reply_transcript(ws, inbound)
                elif inbound is not None:
                    logger.info(
                        "Received command %s (devcontainer=%s, session=%s)",
                        inbound.type,
                        inbound.devcontainer_id,
                        inbound.agent_session_id,
                    )
                    queue.put_nowait(inbound)
        finally:
            consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer

    async def _consume(self, queue: "asyncio.Queue[Command]", ws: Any) -> None:
        emit = self._make_emit(ws)
        emit_delta = self._make_emit_delta(ws)
        while True:
            command = await queue.get()
            try:
                await self._handler(command, emit, emit_delta)
            finally:
                queue.task_done()

    async def _reply_transcript(self, ws: Any, request: TranscriptRequestEnvelope) -> None:
        logger.info(
            "Received transcript_request (request_id=%s, session=%s)",
            request.request_id,
            request.agent_session_id,
        )
        turns = await self._transcript_handler(request.agent_session_id)
        await ws.send(
            json.dumps(
                TranscriptResponseEnvelope(request_id=request.request_id, turns=turns).model_dump()
            )
        )

    def _make_emit(self, ws: Any) -> EmitFn:
        async def emit(event: RuntimeEvent) -> None:
            logger.info(
                "Emitting event %s (devcontainer=%s, session=%s, payload_keys=%s)",
                event.event_type,
                event.devcontainer_id,
                event.agent_session_id,
                sorted((event.payload or {}).keys()),
            )
            await ws.send(json.dumps(RuntimeEventEnvelope(event=event).model_dump()))

        return emit

    def _make_emit_delta(self, ws: Any) -> EmitDeltaFn:
        async def emit_delta(envelope: TurnDeltaEnvelope) -> None:
            await ws.send(json.dumps(envelope.model_dump()))

        return emit_delta
