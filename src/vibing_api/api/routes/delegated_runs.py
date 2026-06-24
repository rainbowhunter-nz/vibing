from fastapi import APIRouter, Request

from vibing_api.api.schemas.delegated_runs import DelegatedRunItem, DelegatedRunList
from vibing_api.core.errors import DevcontainerNotFoundError

router = APIRouter(tags=["delegated-runs"], prefix="/devcontainers")


@router.get("/{devcontainer_id}/delegated-runs", response_model=DelegatedRunList)
def list_delegated_runs(devcontainer_id: str, request: Request) -> DelegatedRunList:
    if request.app.state.devcontainer_store.get(devcontainer_id) is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    items = request.app.state.live_state.get_delegated_runs(devcontainer_id) or []
    return DelegatedRunList(items=[DelegatedRunItem(**it.model_dump()) for it in items])
