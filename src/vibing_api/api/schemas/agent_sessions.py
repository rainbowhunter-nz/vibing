from pydantic import BaseModel, ConfigDict, Field

from vibing_api.core.vocabularies import AgentSessionStatus


class AgentSessionStartRequest(BaseModel):
    prompt: str = Field(min_length=1)


class UserInputRequest(BaseModel):
    inbox_event_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class AgentSession(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    devcontainer_id: str
    status: AgentSessionStatus
    started_at: str | None
    ended_at: str | None
    last_event_at: str | None
    created_at: str
    updated_at: str
