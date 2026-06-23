from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from vibing_api.api.schemas.harnesses import HarnessStatusItem, HarnessStatusList
from vibing_api.core import harness_service
from vibing_api.core.database import get_connection
from vibing_api.core.devcontainer_executor import DevcontainerExecutor
from vibing_api.core.errors import DevcontainerNotFoundError
from vibing_api.core.live_state import LiveStateStore
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository

router = APIRouter(tags=["harnesses"], prefix="/devcontainers")


def _executor(request: Request, devcontainer_id: str) -> DevcontainerExecutor:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    return DevcontainerExecutor(resolved.local_path)


@router.get("/{devcontainer_id}/harnesses", response_model=HarnessStatusList)
def list_harnesses(devcontainer_id: str, request: Request) -> HarnessStatusList:
    live: LiveStateStore = request.app.state.live_state
    cached = live.get_harness(devcontainer_id)
    if cached is None:
        return HarnessStatusList(items=[], known=False)
    return HarnessStatusList(items=[HarnessStatusItem.from_status(s) for s in cached], known=True)


@router.post("/{devcontainer_id}/harnesses/refresh", response_model=HarnessStatusList)
async def refresh_harnesses(devcontainer_id: str, request: Request) -> HarnessStatusList:
    live: LiveStateStore = request.app.state.live_state
    broadcaster = getattr(request.app.state, "broadcaster", None)
    ex = _executor(request, devcontainer_id)
    statuses = await harness_service.refresh(live, devcontainer_id, ex, broadcaster)
    return HarnessStatusList(items=[HarnessStatusItem.from_status(s) for s in statuses], known=True)


def _stream_then_refresh(request: Request, devcontainer_id: str, gen) -> StreamingResponse:
    live: LiveStateStore = request.app.state.live_state
    broadcaster = getattr(request.app.state, "broadcaster", None)
    ex = _executor(request, devcontainer_id)

    async def body() -> AsyncIterator[str]:
        try:
            async for line in gen(ex):
                yield line + "\n"
        finally:
            await harness_service.refresh(live, devcontainer_id, ex, broadcaster)

    return StreamingResponse(body(), media_type="text/plain")


@router.post("/{devcontainer_id}/harnesses/{name}/install", status_code=status.HTTP_200_OK)
def install_harness(devcontainer_id: str, name: str, request: Request) -> StreamingResponse:
    return _stream_then_refresh(
        request, devcontainer_id, lambda ex: harness_service.install_stream(ex, name)
    )


@router.post("/{devcontainer_id}/harnesses/{name}/authenticate", status_code=status.HTTP_200_OK)
def authenticate_harness(devcontainer_id: str, name: str, request: Request) -> StreamingResponse:
    with get_connection() as conn:
        blob = HarnessCredentialRepository(conn).get(name) or {}
    return _stream_then_refresh(
        request, devcontainer_id, lambda ex: harness_service.authenticate_stream(ex, name, blob)
    )
