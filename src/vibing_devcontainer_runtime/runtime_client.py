"""Runtime-channel WebSocket client: outbound-only reconnect loop.

Connects to the Control Plane runtime WebSocket (ADR-0003), registers, and drains
inbound frames (channel is outbound-only — no Commands). Connection failures and
disconnects trigger reconnection with bounded exponential backoff.
"""

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from logzero import logger
from pydantic import BaseModel
from vibing_protocol import RegisterEnvelope, encode


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
    """Connects to the Control Plane runtime channel and sends outbound envelopes."""

    def __init__(
        self,
        control_plane_url: str,
        register: RegisterEnvelope,
        on_registered: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._url = control_plane_url
        self._register = register
        self._on_registered = on_registered
        self._backoff = Backoff()
        self._stopped = False
        self._ws: Any | None = None

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
            await ws.send(encode(self._register))
            logger.info("Registered with control plane")
            if self._on_registered is not None:
                await self._on_registered()
            while not self._stopped:
                await ws.recv()  # drain; channel is outbound-only
        finally:
            self._ws = None

    async def send_envelope(self, envelope: BaseModel) -> None:
        """Send an envelope to the control plane (e.g. Delegated Run events)."""
        ws = self._ws
        if ws is None:
            logger.warning("Dropping %s: runtime channel not connected", type(envelope).__name__)
            return
        await ws.send(encode(envelope))
