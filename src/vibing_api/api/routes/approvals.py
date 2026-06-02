from fastapi import APIRouter

from vibing_api.api.schemas.approvals import ApprovalRequest, ApprovalRequestList
from vibing_api.core.database import get_connection
from vibing_api.core.errors import ApprovalRequestNotFoundError
from vibing_api.repositories.approvals import ApprovalRepository

router = APIRouter(tags=["approvals"], prefix="/approval-requests")


@router.get("", response_model=ApprovalRequestList)
def list_approval_requests(
    status: str | None = None,
    devcontainer_id: str | None = None,
) -> ApprovalRequestList:
    with get_connection() as conn:
        rows = ApprovalRepository(conn).list(status=status, devcontainer_id=devcontainer_id)
    return ApprovalRequestList(items=[ApprovalRequest.model_validate(r) for r in rows])


@router.get("/{approval_request_id}", response_model=ApprovalRequest)
def get_approval_request(approval_request_id: str) -> ApprovalRequest:
    with get_connection() as conn:
        approval = ApprovalRepository(conn).get(approval_request_id)
    if approval is None:
        raise ApprovalRequestNotFoundError(approval_request_id)
    return ApprovalRequest.model_validate(approval)
