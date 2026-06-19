"""HarnessManager: drives adapters for status queries and the authenticate_harness command."""

import asyncio
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessAdapter, HarnessStatus


class HarnessManager:
    def __init__(self, adapters: dict[str, HarnessAdapter]) -> None:
        self._adapters = adapters

    async def _status(self, adapter: HarnessAdapter) -> HarnessStatus:
        installed = await adapter.is_installed()
        authenticated = await adapter.is_authenticated() if installed else False
        return HarnessStatus(name=adapter.name, installed=installed, authenticated=authenticated)

    async def list_statuses(self) -> list[HarnessStatus]:
        return list(await asyncio.gather(*(self._status(a) for a in self._adapters.values())))

    async def authenticate(self, harness: str, blob: dict[str, Any]) -> HarnessStatus:
        adapter = self._adapters[harness]  # KeyError on unknown harness
        if not await adapter.is_installed():
            await adapter.install()
        adapter.write_credentials(blob)
        return await self._status(adapter)
