from typing import Literal

DevcontainerStatus = Literal["created", "starting", "running", "stopping", "stopped", "error"]
AgentSessionStatus = Literal[
    "starting", "running", "waiting_for_approval", "completed", "failed", "stopped"
]
ApprovalStatus = Literal["pending", "approved", "rejected"]
InboxEventType = Literal["question", "approval_request", "completion", "failure"]
