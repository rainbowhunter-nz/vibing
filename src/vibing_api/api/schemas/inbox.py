from pydantic import BaseModel, ConfigDict

from vibing_api.api.schemas.agent_sessions import AgentSession
from vibing_api.api.schemas.approvals import ApprovalRequest
from vibing_api.api.schemas.devcontainers import Devcontainer
from vibing_api.core.vocabularies import InboxEventType


class InboxEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    devcontainer_id: str
    agent_session_id: str | None
    approval_request_id: str | None
    event_type: InboxEventType
    status: str
    created_at: str
    updated_at: str


class InboxEventList(BaseModel):
    items: list[InboxEvent]


class InboxEventDetail(InboxEvent):
    devcontainer: Devcontainer
    agent_session: AgentSession | None
    approval_request: ApprovalRequest | None
