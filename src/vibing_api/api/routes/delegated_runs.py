from fastapi import APIRouter

from vibing_api.api.schemas.delegated_runs import DelegatedRunList
from vibing_api.core.database import get_connection
from vibing_api.core.errors import DevcontainerNotFoundError
from vibing_api.repositories.devcontainers import DevcontainerRepository

router = APIRouter(tags=["delegated-runs"], prefix="/devcontainers")


@router.get("/{devcontainer_id}/delegated-runs", response_model=DelegatedRunList)
def list_delegated_runs(devcontainer_id: str) -> DelegatedRunList:
    # FE↔BE deferred: the Control Plane stores Delegated Runs (ADR-0016) but does
    # not yet surface them to the web UI. This endpoint stays empty so RailActivity
    # reads as genuinely empty; flipping it to read DelegatedRunRepository is the
    # deferred frontend-facing step.
    with get_connection() as conn:
        if DevcontainerRepository(conn).get(devcontainer_id) is None:
            raise DevcontainerNotFoundError(devcontainer_id)
    return DelegatedRunList(items=[])
