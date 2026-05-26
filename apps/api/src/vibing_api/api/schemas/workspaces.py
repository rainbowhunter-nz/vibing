from typing import Literal

from pydantic import BaseModel, Field

WorkspaceStatus = Literal[
    "created",
    "starting",
    "running",
    "stopping",
    "stopped",
    "error",
    "deleted",
]


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    local_path: str = Field(min_length=1)


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    status: WorkspaceStatus | None = None


class Workspace(BaseModel):
    id: str
    name: str
    local_path: str
    status: str
    created_at: str
    updated_at: str


class WorkspaceList(BaseModel):
    items: list[Workspace]
