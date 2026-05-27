from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, field_validator

from vibing_api.core import settings_store
from vibing_api.core.config import settings

router = APIRouter(tags=["settings"])


class RuntimeDetection(BaseModel):
    docker: bool | None = None
    podman: bool | None = None
    devcontainer_cli: bool | None = None
    claude_code: bool | None = None


class SettingsResponse(BaseModel):
    workspace_storage_location: str
    backend_host: str
    backend_port: int
    editor_preference: str | None = None
    notifications_enabled: bool | None = None
    runtime: RuntimeDetection


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_storage_location: str

    @field_validator("workspace_storage_location")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("workspace_storage_location must not be empty")
        return stripped


def detect_runtimes() -> RuntimeDetection:
    # Detection lands in a later ticket; the fields exist now, all unknown.
    return RuntimeDetection()


def _build_response(stored: settings_store.StoredSettings) -> SettingsResponse:
    return SettingsResponse(
        workspace_storage_location=stored.workspace_storage_location,
        backend_host=settings.backend_host,
        backend_port=settings.backend_port,
        editor_preference=None,
        notifications_enabled=None,
        runtime=detect_runtimes(),
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return _build_response(settings_store.load())


@router.patch("/settings", response_model=SettingsResponse)
def update_settings(update: SettingsUpdate) -> SettingsResponse:
    stored = settings_store.update(update.workspace_storage_location)
    return _build_response(stored)
