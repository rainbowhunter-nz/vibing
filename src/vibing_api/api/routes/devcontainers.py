from fastapi import APIRouter, Request, Response, status

from vibing_api.api.schemas.devcontainers import (
    Devcontainer,
    DevcontainerCreateRequest,
    DevcontainerUpdateRequest,
    DevcontainerView,
    DevcontainerViewList,
    RuntimeConnection,
)
from vibing_api.core.database import get_connection
from vibing_api.core.devcontainer_service import DevcontainerService, run_in_background
from vibing_api.core.errors import DevcontainerNotFoundError, InvalidDevcontainerStateError
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.core.vocabularies import DevcontainerStatus
from vibing_api.repositories.devcontainers import DevcontainerRepository

router = APIRouter(tags=["devcontainers"], prefix="/devcontainers")

_START_ALLOWED_FROM = frozenset(
    {DevcontainerStatus.CREATED, DevcontainerStatus.STOPPED, DevcontainerStatus.ERROR}
)
_STOP_ALLOWED_FROM = frozenset({DevcontainerStatus.RUNNING, DevcontainerStatus.ERROR})


@router.post("", response_model=Devcontainer, status_code=status.HTTP_201_CREATED)
def create_devcontainer(payload: DevcontainerCreateRequest) -> Devcontainer:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).create(payload.name, payload.local_path)
        conn.commit()
    return devcontainer


def _with_runtime(
    devcontainer: Devcontainer, *, runtime_manager: RuntimeRegistry
) -> DevcontainerView:
    runtime = RuntimeConnection(runtime_connected=runtime_manager.is_connected(devcontainer.id))
    return DevcontainerView(**devcontainer.model_dump(), runtime=runtime)


@router.get("", response_model=DevcontainerViewList)
def list_devcontainers(request: Request) -> DevcontainerViewList:
    with get_connection() as conn:
        items = DevcontainerRepository(conn).list()
    runtime_manager: RuntimeRegistry = request.app.state.runtime_manager
    views = [_with_runtime(item, runtime_manager=runtime_manager) for item in items]
    return DevcontainerViewList(items=views)


@router.get("/{devcontainer_id}", response_model=DevcontainerView)
def get_devcontainer(devcontainer_id: str, request: Request) -> DevcontainerView:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    return _with_runtime(devcontainer, runtime_manager=request.app.state.runtime_manager)


@router.patch("/{devcontainer_id}", response_model=Devcontainer)
def update_devcontainer(devcontainer_id: str, payload: DevcontainerUpdateRequest) -> Devcontainer:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).update(
            devcontainer_id, name=payload.name, status=payload.status
        )
        conn.commit()
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    return devcontainer


@router.delete("/{devcontainer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_devcontainer(devcontainer_id: str) -> Response:
    with get_connection() as conn:
        deleted = DevcontainerRepository(conn).delete(devcontainer_id)
        conn.commit()
    if not deleted:
        raise DevcontainerNotFoundError(devcontainer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{devcontainer_id}/start", response_model=Devcontainer, status_code=202)
async def start_devcontainer(devcontainer_id: str, request: Request) -> Devcontainer:
    return await _dispatch_lifecycle(devcontainer_id, request, "start", _START_ALLOWED_FROM)


@router.post("/{devcontainer_id}/stop", response_model=Devcontainer, status_code=202)
async def stop_devcontainer(devcontainer_id: str, request: Request) -> Devcontainer:
    return await _dispatch_lifecycle(devcontainer_id, request, "stop", _STOP_ALLOWED_FROM)


async def _dispatch_lifecycle(
    devcontainer_id: str,
    request: Request,
    action: str,
    allowed_from: frozenset[DevcontainerStatus],
) -> Devcontainer:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    if devcontainer.status not in allowed_from:
        raise InvalidDevcontainerStateError(action, devcontainer.status, allowed_from)
    service: DevcontainerService = request.app.state.devcontainer_service
    coro = (
        service.start(devcontainer.id, devcontainer.local_path)
        if action == "start"
        else service.stop(devcontainer.id, devcontainer.local_path)
    )
    run_in_background(coro)
    return devcontainer
