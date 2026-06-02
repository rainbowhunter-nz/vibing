from pydantic import BaseModel, ConfigDict

from vibing_api.core.vocabularies import ApprovalStatus


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    devcontainer_id: str
    agent_session_id: str
    status: ApprovalStatus
    requested_action: str
    created_at: str
    decided_at: str | None


class ApprovalRequestList(BaseModel):
    items: list[ApprovalRequest]
