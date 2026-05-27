from fastapi import APIRouter
from pydantic import BaseModel

from vibing_api.core.config import settings

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
