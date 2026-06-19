from fastapi import APIRouter, Request, status
from vibing_protocol import Command, CommandType

from vibing_api.api.schemas.harnesses import HarnessStatusItem, HarnessStatusList
from vibing_api.core.database import get_connection
from vibing_api.core.errors import DevcontainerNotFoundError, RuntimeUnavailableError
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository
from vibing_api.repositories.harness_status import HarnessStatusRepository

router = APIRouter(tags=["harnesses"], prefix="/devcontainers")


@router.get("/{devcontainer_id}/harnesses", response_model=HarnessStatusList)
def list_harnesses(devcontainer_id: str) -> HarnessStatusList:
    with get_connection() as conn:
        dc = DevcontainerRepository(conn).get(devcontainer_id)
        if dc is None:
            raise DevcontainerNotFoundError(devcontainer_id)
        rows = HarnessStatusRepository(conn).list(devcontainer_id)
    return HarnessStatusList(
        items=[
            HarnessStatusItem(name=r.name, installed=r.installed, authenticated=r.authenticated)
            for r in rows
        ]
    )


@router.post(
    "/{devcontainer_id}/harnesses/{name}/authenticate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def authenticate_harness(devcontainer_id: str, name: str, request: Request) -> dict:
    runtime_manager: RuntimeRegistry = request.app.state.runtime_manager
    if not runtime_manager.is_connected(devcontainer_id):
        raise RuntimeUnavailableError(f"No runtime connected for devcontainer {devcontainer_id!r}")
    with get_connection() as conn:
        credentials = HarnessCredentialRepository(conn).get(name) or {}
    command = Command(
        type=CommandType.AUTHENTICATE_HARNESS,
        devcontainer_id=devcontainer_id,
        payload={"harness": name, "credentials": credentials},
    )
    await runtime_manager.send_command(devcontainer_id, command)
    return {}
