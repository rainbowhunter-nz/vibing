"""HarnessCommandHandler: authenticate_harness only; reports HarnessStatus back."""

from collections.abc import Awaitable, Callable

from logzero import logger
from pydantic import BaseModel
from vibing_protocol import Command, CommandType, HarnessStatusEnvelope, HarnessStatusItem

from vibing_devcontainer_runtime.harness_manager import HarnessManager

SendFn = Callable[[BaseModel], Awaitable[None]]


class HarnessCommandHandler:
    def __init__(self, harness_manager: HarnessManager, devcontainer_id: str) -> None:
        self._harness = harness_manager
        self._devcontainer_id = devcontainer_id

    async def handle(self, command: Command, send: SendFn) -> None:
        if command.type != CommandType.AUTHENTICATE_HARNESS:
            logger.info("Ignoring unsupported command: %s", command.type)
            return
        payload = command.payload or {}
        status = await self._harness.authenticate(
            payload.get("harness", ""), payload.get("credentials") or {}
        )
        await send(self._envelope([status]))

    def _envelope(self, statuses) -> HarnessStatusEnvelope:
        return HarnessStatusEnvelope(
            devcontainer_id=self._devcontainer_id,
            items=[
                HarnessStatusItem(name=s.name, installed=s.installed, authenticated=s.authenticated)
                for s in statuses
            ],
        )

    async def report_all(self, send: SendFn) -> None:
        await send(self._envelope(await self._harness.list_statuses()))
