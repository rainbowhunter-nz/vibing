"""Runtime lifecycle orchestration (ADR-0017).

Owns the `launching` transient and its timeout, runtime stop, and live log streaming.
The WebSocket (RuntimeRegistry) is the durable liveness truth; this service only
manages the transient launching window and the control actions.
"""

import asyncio
from collections.abc import AsyncIterator

from logzero import logger

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.devcontainer_service import run_in_background
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.core.runtime_injector import RuntimeInjector
from vibing_api.core.vocabularies import RuntimeState


class RuntimeService:
    def __init__(
        self,
        injector: RuntimeInjector,
        *,
        live_state: LiveStateStore,
        registry: RuntimeRegistry,
        broadcaster: Broadcaster | None = None,
        launch_timeout: float = 30.0,
    ) -> None:
        self._injector = injector
        self._live = live_state
        self._registry = registry
        self._broadcaster = broadcaster
        self._launch_timeout = launch_timeout

    def _publish(self, devcontainer_id: str) -> None:
        if self._broadcaster is not None:
            self._broadcaster.publish(SseEvent(scope="runtime", ids=[devcontainer_id]))

    async def inject(self, devcontainer_id: str, local_path: str) -> None:
        self._live.set_runtime_transient(devcontainer_id, RuntimeState.LAUNCHING)
        self._publish(devcontainer_id)
        launched = await self._injector.inject_by_path(devcontainer_id, local_path)
        if not launched:
            self._live.set_runtime_transient(devcontainer_id, RuntimeState.ERROR)
            self._publish(devcontainer_id)
            return
        run_in_background(self._expire_launching(devcontainer_id))

    async def _expire_launching(self, devcontainer_id: str) -> None:
        await asyncio.sleep(self._launch_timeout)
        if self._registry.is_connected(devcontainer_id):
            return
        if self._live.get_runtime_transient(devcontainer_id) == RuntimeState.LAUNCHING:
            logger.info("runtime launch timed out: %s (-> disconnected)", devcontainer_id)
            self._live.clear_runtime_transient(devcontainer_id)
            self._publish(devcontainer_id)

    async def stop(self, devcontainer_id: str, local_path: str) -> None:
        await self._injector.stop_runtime(local_path)
        self._live.clear_runtime_transient(devcontainer_id)
        self._publish(devcontainer_id)

    def stream_log(self, local_path: str) -> AsyncIterator[bytes]:
        return self._injector.stream_log(local_path)
