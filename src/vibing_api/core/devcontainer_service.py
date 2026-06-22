"""In-process Devcontainer lifecycle (ADR-0014, live-state model).

Shells out to the Dev Container CLI; reflects in-flight status in the in-memory
LiveStateStore (no DB status). Runtime injection is now an explicit endpoint, not
an automatic post-start step. Long ops run in a background task; routes return 202.
"""

import asyncio

from logzero import logger

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.devcontainer_cli import DevcontainerCliAdapter, DevcontainerFailure
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.vocabularies import DevcontainerStatus


class DevcontainerService:
    def __init__(
        self,
        adapter: DevcontainerCliAdapter,
        *,
        live_state: LiveStateStore,
        broadcaster: Broadcaster | None = None,
    ) -> None:
        self._adapter = adapter
        self._live = live_state
        self._broadcaster = broadcaster

    def _publish(self, devcontainer_id: str) -> None:
        if self._broadcaster is not None:
            self._broadcaster.publish(SseEvent(scope="devcontainers", ids=[devcontainer_id]))

    def _set(self, devcontainer_id: str, status: DevcontainerStatus) -> None:
        self._live.set_transient(devcontainer_id, status)
        self._publish(devcontainer_id)

    def _clear(self, devcontainer_id: str) -> None:
        self._live.clear_transient(devcontainer_id)
        self._publish(devcontainer_id)

    async def start(self, devcontainer_id: str, local_path: str) -> None:
        logger.info("devcontainer start: %s (%s)", devcontainer_id, local_path)
        self._set(devcontainer_id, DevcontainerStatus.STARTING)
        result = await self._adapter.start(local_path)
        if isinstance(result, DevcontainerFailure):
            _log_failure(devcontainer_id, result)
            self._set(devcontainer_id, DevcontainerStatus.ERROR)
            return
        logger.info("devcontainer started: %s", devcontainer_id)
        self._clear(devcontainer_id)

    async def stop(self, devcontainer_id: str, local_path: str) -> None:
        logger.info("devcontainer stop: %s (%s)", devcontainer_id, local_path)
        self._set(devcontainer_id, DevcontainerStatus.STOPPING)
        result = await self._adapter.stop(local_path)
        if isinstance(result, DevcontainerFailure):
            _log_failure(devcontainer_id, result)
            self._set(devcontainer_id, DevcontainerStatus.ERROR)
            return
        logger.info("devcontainer stopped: %s", devcontainer_id)
        self._clear(devcontainer_id)


def _log_failure(devcontainer_id: str, failure: DevcontainerFailure) -> None:
    logger.error(
        "devcontainer %s failed (%s): %s\ncommand: %s\nstderr:\n%s",
        failure.operation,
        devcontainer_id,
        failure.message,
        " ".join(failure.command),
        failure.stderr_tail or "(empty)",
    )


_background_tasks: set[asyncio.Task[None]] = set()


def run_in_background(coro) -> "asyncio.Task[None]":
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
