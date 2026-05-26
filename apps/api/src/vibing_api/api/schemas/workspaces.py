from pydantic import BaseModel, Field


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    local_path: str = Field(min_length=1)


class Workspace(BaseModel):
    id: str
    name: str
    local_path: str
    status: str
    created_at: str
    updated_at: str


class WorkspaceList(BaseModel):
    items: list[Workspace]
