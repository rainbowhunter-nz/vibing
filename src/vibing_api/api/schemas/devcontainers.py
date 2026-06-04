from pydantic import BaseModel, Field

from vibing_api.core.vocabularies import DevcontainerStatus


class DevcontainerCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    local_path: str = Field(min_length=1)


class DevcontainerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    status: DevcontainerStatus | None = None


class Devcontainer(BaseModel):
    id: str
    name: str
    local_path: str
    status: DevcontainerStatus
    created_at: str
    updated_at: str


class DevcontainerList(BaseModel):
    items: list[Devcontainer]


class RuntimeConnection(BaseModel):
    worker_connected: bool
    agent_connected: bool


class DevcontainerView(Devcontainer):
    runtime: RuntimeConnection


class DevcontainerViewList(BaseModel):
    items: list[DevcontainerView]


class RuntimeStatus(BaseModel):
    worker_connected: bool
