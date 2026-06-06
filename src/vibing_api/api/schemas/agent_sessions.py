from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from vibing_protocol import TranscriptTurn

from vibing_api.core.vocabularies import AgentSessionStatus


class AgentSessionStartRequest(BaseModel):
    prompt: str = Field(min_length=1)


class UserInputRequest(BaseModel):
    inbox_event_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ApprovalResolutionRequest(BaseModel):
    approval_request_id: str = Field(min_length=1)
    resolution: Literal["approved", "rejected"]


class AgentSession(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    devcontainer_id: str
    status: AgentSessionStatus
    prompt: str | None = None
    started_at: str | None
    ended_at: str | None
    last_event_at: str | None
    created_at: str
    updated_at: str


class AgentSessionDetail(AgentSession):
    summary_text: str | None = None


class AgentSessionList(BaseModel):
    items: list[AgentSession]


TranscriptState = Literal["has_turns", "empty", "summary_fallback", "error"]


class AgentSessionTranscript(BaseModel):
    """Live transcript fetch result (ADR-0009). `state` lets the frontend distinguish
    has-turns / empty ("no conversation yet") / summary-fallback (stopped) / error.
    Transcript content is never persisted."""

    state: TranscriptState
    turns: list[TranscriptTurn] = Field(default_factory=list)
    summary_text: str | None = None
