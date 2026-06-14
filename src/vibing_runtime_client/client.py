"""Shared runtime-channel WebSocket client: reconnect loop and command queue.

Connects to the Control Plane runtime WebSocket (ADR-0003), registers, and serially
processes the Commands it receives. Connection failures and disconnects trigger
reconnection with bounded exponential backoff. The command queue is in-memory and
per-session, so in-flight Commands are never replayed after a disconnect or process exit.

The channel carries three message patterns (ADR-0009): commands in, envelopes out
(via the `send` passed to the command handler), and request/reply correlated by the
caller-registered responder (`on_request`). The client knows no domain message types
beyond Command itself.
"""

import asyncio
import contextlib
import json
import signal
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from logzero import logger
from pydantic import BaseModel, ValidationError
from vibing_protocol import Command, CommandEnvelope, RegisterEnvelope

SendFn = Callable[[BaseModel], Awaitable[None]]
CommandHandler = Callable[[Command, SendFn], Awaitable[None]]
# Receives the raw request message, returns the reply envelope (correlation id included).
RequestHandler = Callable[[dict[str, Any]], Awaitable[BaseModel]]


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


class RuntimeChannelClient:
    """Connects to the Control Plane runtime channel and serially runs received Commands."""

    def __init__(
        self, control_plane_url: str, register: RegisterEnvelope, handler: CommandHandler
    ) -> None:
        self._url = control_plane_url
        self._register = register
        self._handler = handler
        self._request_handlers: dict[str, RequestHandler] = {}
        self._backoff = Backoff()
        self._stopped = False
        self._ws: Any | None = None

    def on_request(self, message_type: str, respond: RequestHandler) -> None:
        """Register the responder for one request/reply message type (ADR-0009)."""
        self._request_handlers[message_type] = respond

    def stop(self) -> None:
        self._stopped = True
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                asyncio.get_running_loop().create_task(ws.close())

    def run_blocking(self) -> None:
        """Run until SIGTERM/SIGINT, then stop cleanly. Sync entry point for CLIs."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        main = loop.create_task(self.run())

        def _stop() -> None:
            self.stop()
            main.cancel()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _stop)

        try:
            loop.run_until_complete(main)
        except asyncio.CancelledError:
            pass
        finally:
            loop.close()

    async def run(self) -> None:
        """Reconnect forever (until stopped), backing off between attempts."""
        while not self._stopped:
            try:
                async with websockets.connect(self._url) as ws:
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
            await asyncio.sleep(delay)

    async def _run_session(self, ws: Any) -> None:
        self._ws = ws
        try:
            await ws.send(json.dumps(self._register.model_dump()))
            logger.info("Registered with control plane; awaiting commands")
            send = self._make_send(ws)
            queue: asyncio.Queue[Command] = asyncio.Queue()
            consumer = asyncio.create_task(self._consume(queue, send))
            try:
                while not self._stopped:
                    message = _parse_message(await ws.recv())
                    if message is not None:
                        await self._dispatch(message, queue, send)
            finally:
                consumer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await consumer
        finally:
            self._ws = None

    async def _dispatch(
        self, message: dict[str, Any], queue: "asyncio.Queue[Command]", send: SendFn
    ) -> None:
        msg_type = message.get("type")
        if msg_type == "command":
            try:
                command = CommandEnvelope.model_validate(message).command
            except ValidationError:
                return
            logger.info(
                "Received command %s (devcontainer=%s, session=%s)",
                command.type,
                command.devcontainer_id,
                command.agent_session_id,
            )
            queue.put_nowait(command)
            return
        respond = self._request_handlers.get(msg_type) if isinstance(msg_type, str) else None
        if respond is None:
            return
        logger.info("Received request %s", msg_type)
        try:
            reply = await respond(message)
        except Exception:
            # No reply on failure; the Control Plane's request timeout handles it (ADR-0009).
            logger.exception("Request handler for %s failed", msg_type)
            return
        await send(reply)

    async def _consume(self, queue: "asyncio.Queue[Command]", send: SendFn) -> None:
        while True:
            command = await queue.get()
            try:
                await self._handler(command, send)
            finally:
                queue.task_done()

    def _make_send(self, ws: Any) -> SendFn:
        async def send(envelope: BaseModel) -> None:
            await ws.send(json.dumps(envelope.model_dump()))

        return send


def _parse_message(raw: str) -> dict[str, Any] | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None
