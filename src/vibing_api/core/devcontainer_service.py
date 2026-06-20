"""In-process Devcontainer lifecycle (ADR-0014).

The Control Plane shells out to the Dev Container CLI directly, writes status to the read
model as it progresses, and injects the Devcontainer Runtime after a successful start.
Long ops run in a background task; routes return 202.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from logzero import logger

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.database import get_connection
from vibing_api.core.devcontainer_cli import DevcontainerCliAdapter, DevcontainerFailure
from vibing_api.core.runtime_injector import RuntimeInjector
from vibing_api.core.vocabularies import DevcontainerStatus


class DevcontainerService:
    def __init__(
        self,
        adapter: DevcontainerCliAdapter,
        injector: RuntimeInjector,
        *,
        broadcaster: Broadcaster | None = None,
        repo_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._adapter = adapter
        self._injector = injector
        self._broadcaster = broadcaster
        self._repo_factory = repo_factory

    def _set_status(self, devcontainer_id: str, status: DevcontainerStatus) -> None:
        if self._repo_factory is not None:
            self._repo_factory().update(devcontainer_id, status=status)  # test seam
        else:
            from vibing_api.repositories.devcontainers import DevcontainerRepository

            with get_connection() as conn:
                DevcontainerRepository(conn).update(devcontainer_id, status=status)
                conn.commit()
        if self._broadcaster is not None:
            self._broadcaster.publish(SseEvent(scope="devcontainers", ids=[devcontainer_id]))

    async def start(self, devcontainer_id: str, local_path: str) -> None:
        self._set_status(devcontainer_id, DevcontainerStatus.STARTING)
        result = await self._adapter.start(local_path)
        if isinstance(result, DevcontainerFailure):
            logger.error("devcontainer start failed (%s): %s", devcontainer_id, result.message)
            self._set_status(devcontainer_id, DevcontainerStatus.ERROR)
            return
        self._set_status(devcontainer_id, DevcontainerStatus.RUNNING)
        container_id = result.payload.get("container_id")
        if container_id:
            try:
                await self._injector.inject(devcontainer_id, container_id, local_path)
            except Exception:
                logger.warning("runtime injection failed for %s; ignoring", devcontainer_id)
        else:
            logger.warning(
                "no container_id in up output for %s; skipping injection", devcontainer_id
            )

    async def stop(self, devcontainer_id: str, local_path: str) -> None:
        self._set_status(devcontainer_id, DevcontainerStatus.STOPPING)
        result = await self._adapter.stop(local_path)
        if isinstance(result, DevcontainerFailure):
            logger.error("devcontainer stop failed (%s): %s", devcontainer_id, result.message)
            self._set_status(devcontainer_id, DevcontainerStatus.ERROR)
            return
        self._set_status(devcontainer_id, DevcontainerStatus.STOPPED)


def run_in_background(coro) -> "asyncio.Task[None]":
    return asyncio.create_task(coro)
