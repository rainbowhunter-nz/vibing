from fastapi import APIRouter, status
from pydantic import BaseModel

from vibing_api.core.config import settings
from vibing_api.core.database import get_connection
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository

router = APIRouter(tags=["settings"])


class RuntimeDetection(BaseModel):
    docker: bool | None = None
    podman: bool | None = None
    devcontainer_cli: bool | None = None
    claude_code: bool | None = None


class SettingsResponse(BaseModel):
    backend_host: str
    backend_port: int
    runtime: RuntimeDetection


class HarnessCredentialView(BaseModel):
    name: str
    configured: bool


class HarnessCredentialUpsertRequest(BaseModel):
    blob: dict


def detect_runtimes() -> RuntimeDetection:
    # Detection lands in a later ticket; the fields exist now, all unknown.
    return RuntimeDetection()


@router.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return SettingsResponse(
        backend_host=settings.backend_host,
        backend_port=settings.backend_port,
        runtime=detect_runtimes(),
    )


@router.get("/settings/harness-credentials", response_model=list[HarnessCredentialView])
def list_harness_credentials() -> list[HarnessCredentialView]:
    with get_connection() as conn:
        names = HarnessCredentialRepository(conn).list()
    return [HarnessCredentialView(name=n, configured=True) for n in names]


@router.put(
    "/settings/harness-credentials/{name}",
    response_model=HarnessCredentialView,
    status_code=status.HTTP_200_OK,
)
def upsert_harness_credential(
    name: str, payload: HarnessCredentialUpsertRequest
) -> HarnessCredentialView:
    with get_connection() as conn:
        HarnessCredentialRepository(conn).upsert(name, payload.blob)
        conn.commit()
    return HarnessCredentialView(name=name, configured=True)
