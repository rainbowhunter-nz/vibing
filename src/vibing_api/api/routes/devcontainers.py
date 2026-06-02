from fastapi import APIRouter, Request, Response, status
from vibing_protocol import Command, CommandType

from vibing_api.api.schemas.devcontainers import (
    Devcontainer,
    DevcontainerCreateRequest,
    DevcontainerList,
    DevcontainerUpdateRequest,
)
from vibing_api.core.database import get_connection
from vibing_api.core.errors import (
    DevcontainerNotFoundError,
    InvalidDevcontainerStateError,
    RuntimeUnavailableError,
)
from vibing_api.core.runtime_channel import WORKER_SLOT, WorkerRegistry
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


@router.get("", response_model=DevcontainerList)
def list_devcontainers() -> DevcontainerList:
    with get_connection() as conn:
        items = DevcontainerRepository(conn).list()
    return DevcontainerList(items=items)


@router.get("/{devcontainer_id}", response_model=Devcontainer)
def get_devcontainer(devcontainer_id: str) -> Devcontainer:
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    return devcontainer


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
    return await _dispatch_lifecycle(
        devcontainer_id, request, "start", CommandType.START_DEVCONTAINER, _START_ALLOWED_FROM
    )


@router.post("/{devcontainer_id}/stop", response_model=Devcontainer, status_code=202)
async def stop_devcontainer(devcontainer_id: str, request: Request) -> Devcontainer:
    return await _dispatch_lifecycle(
        devcontainer_id, request, "stop", CommandType.STOP_DEVCONTAINER, _STOP_ALLOWED_FROM
    )


async def _dispatch_lifecycle(
    devcontainer_id: str,
    request: Request,
    action: str,
    command_type: CommandType,
    allowed_from: frozenset[DevcontainerStatus],
) -> Devcontainer:
    """Validate state + worker availability, then send the lifecycle Command.

    The read model is returned unchanged; projected status updates arrive later as
    Runtime Events the worker emits back over the runtime channel.
    """
    with get_connection() as conn:
        devcontainer = DevcontainerRepository(conn).get(devcontainer_id)
    if devcontainer is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    if devcontainer.status not in allowed_from:
        raise InvalidDevcontainerStateError(action, devcontainer.status, allowed_from)

    manager: WorkerRegistry = request.app.state.runtime_manager
    if not manager.is_connected(WORKER_SLOT):
        raise RuntimeUnavailableError()

    await manager.send_command(
        Command(
            type=command_type,
            devcontainer_id=devcontainer.id,
            payload={"local_path": devcontainer.local_path},
        )
    )
    return devcontainer
