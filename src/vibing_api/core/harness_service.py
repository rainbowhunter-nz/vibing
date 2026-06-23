"""Harness setup, Control-Plane-owned (ADR-0019). Drives vibing_harness descriptors
through an injected Executor (DevcontainerExecutor in production). Status is computed
and cached in LiveStateStore; install/auth stream their output for live observability."""

import asyncio
from collections.abc import AsyncIterator

from vibing_harness import Executor, HarnessStatus, descriptors

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.devcontainer_executor import DevcontainerExecutor
from vibing_api.core.live_state import LiveStateStore


async def compute_status(ex: Executor) -> list[HarnessStatus]:
    items = descriptors().values()
    return list(await asyncio.gather(*(d.status(ex) for d in items)))


async def refresh(
    live: LiveStateStore,
    devcontainer_id: str,
    ex: Executor,
    broadcaster: Broadcaster | None = None,
) -> list[HarnessStatus]:
    statuses = await compute_status(ex)
    live.set_harness(devcontainer_id, statuses)  # type: ignore[arg-type]  # Task 7 migrates LiveStateStore to HarnessStatus
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="harnesses", ids=[devcontainer_id]))
    return statuses


async def install_stream(ex: DevcontainerExecutor, name: str) -> AsyncIterator[str]:
    d = descriptors()[name]
    if await d.is_installed(ex):
        yield f"{name} already installed"
        return
    async for line in ex.stream(d.install_argv()):
        yield line


async def authenticate_stream(
    ex: DevcontainerExecutor, name: str, blob: dict
) -> AsyncIterator[str]:
    d = descriptors()[name]
    if not await d.is_installed(ex):
        async for line in ex.stream(d.install_argv()):
            yield line
    await d.write_credentials(ex, blob)
    yield f"{name} authenticated"
