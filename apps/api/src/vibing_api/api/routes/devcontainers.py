from fastapi import APIRouter, Response, status

from vibing_api.api.schemas.devcontainers import (
    Devcontainer,
    DevcontainerCreateRequest,
    DevcontainerList,
    DevcontainerUpdateRequest,
)
from vibing_api.core.database import get_connection
from vibing_api.core.errors import DevcontainerNotFoundError
from vibing_api.repositories.devcontainers import DevcontainerRepository

router = APIRouter(tags=["devcontainers"], prefix="/devcontainers")


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
