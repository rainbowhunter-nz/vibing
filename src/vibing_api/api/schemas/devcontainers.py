from enum import StrEnum, auto

from pydantic import BaseModel, Field

from vibing_api.core.vocabularies import DevcontainerStatus, RuntimeState


class DevcontainerSource(StrEnum):
    MANUAL = auto()
    DISCOVERED = auto()


class DevcontainerCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    local_path: str = Field(min_length=1)


class DevcontainerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)


class Devcontainer(BaseModel):
    id: str
    name: str
    local_path: str
    status: DevcontainerStatus
    source: DevcontainerSource
    created_at: str | None
    updated_at: str | None


class DevcontainerList(BaseModel):
    items: list[Devcontainer]


class RuntimeConnection(BaseModel):
    state: RuntimeState


class RuntimeLogs(BaseModel):
    content: str | None


class DevcontainerView(Devcontainer):
    runtime: RuntimeConnection


class DevcontainerViewList(BaseModel):
    items: list[DevcontainerView]
