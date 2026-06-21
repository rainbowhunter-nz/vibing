from fastapi import APIRouter, Request, Response, status

from vibing_api.api.schemas.devcontainers import (
    Devcontainer,
    DevcontainerCreateRequest,
    DevcontainerSource,
    DevcontainerUpdateRequest,
    DevcontainerView,
    DevcontainerViewList,
    RuntimeConnection,
)
from vibing_api.core.catalog import DevcontainerCatalog, ResolvedDevcontainer
from vibing_api.core.database import get_connection
from vibing_api.core.devcontainer_service import DevcontainerService, run_in_background
from vibing_api.core.errors import DevcontainerNotFoundError, InvalidDevcontainerStateError
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.status_resolver import resolve_status
from vibing_api.core.vocabularies import DevcontainerStatus
from vibing_api.repositories.devcontainers import DevcontainerRepository

router = APIRouter(tags=["devcontainers"], prefix="/devcontainers")

_START_ALLOWED_FROM = frozenset({DevcontainerStatus.STOPPED, DevcontainerStatus.ERROR})
_STOP_ALLOWED_FROM = frozenset({DevcontainerStatus.RUNNING, DevcontainerStatus.ERROR})


async def _view(
    resolved: ResolvedDevcontainer, request: Request, running: set[str] | None = None
) -> DevcontainerView:
    live: LiveStateStore = request.app.state.live_state
    if running is None:
        running = await request.app.state.devcontainer_cli.running_local_folders()
    status_value = resolve_status(live.get_transient(resolved.id), running, resolved.local_path)
    runtime = RuntimeConnection(
        runtime_connected=request.app.state.runtime_manager.is_connected(resolved.id)
    )
    return DevcontainerView(
        id=resolved.id,
        name=resolved.name,
        local_path=resolved.local_path,
        status=status_value,
        source=resolved.source,
        created_at=resolved.created_at,
        updated_at=resolved.updated_at,
        runtime=runtime,
    )


@router.post("", response_model=Devcontainer, status_code=status.HTTP_201_CREATED)
async def create_devcontainer(payload: DevcontainerCreateRequest, request: Request) -> Devcontainer:
    with get_connection() as conn:
        record = DevcontainerRepository(conn).create(payload.name, payload.local_path)
        conn.commit()
    catalog: DevcontainerCatalog = request.app.state.catalog
    resolved = catalog.get(record.id)
    assert resolved is not None  # catalog reads the same DB; a row just committed is always visible
    return await _view(resolved, request)


@router.get("", response_model=DevcontainerViewList)
async def list_devcontainers(request: Request) -> DevcontainerViewList:
    catalog: DevcontainerCatalog = request.app.state.catalog
    running = await request.app.state.devcontainer_cli.running_local_folders()
    views = [await _view(r, request, running) for r in catalog.list()]
    return DevcontainerViewList(items=views)


@router.get("/{devcontainer_id}", response_model=DevcontainerView)
async def get_devcontainer(devcontainer_id: str, request: Request) -> DevcontainerView:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    return await _view(resolved, request)


@router.patch("/{devcontainer_id}", response_model=Devcontainer)
async def update_devcontainer(
    devcontainer_id: str, payload: DevcontainerUpdateRequest, request: Request
) -> Devcontainer:
    with get_connection() as conn:
        updated = DevcontainerRepository(conn).update(devcontainer_id, name=payload.name)
        conn.commit()
    if updated is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    resolved = request.app.state.catalog.get(devcontainer_id)
    assert resolved is not None  # catalog reads the same DB; a row just committed is always visible
    return await _view(resolved, request)


@router.post("/{devcontainer_id}/start", response_model=DevcontainerView, status_code=202)
async def start_devcontainer(devcontainer_id: str, request: Request) -> DevcontainerView:
    return await _dispatch_lifecycle(devcontainer_id, request, "start", _START_ALLOWED_FROM)


@router.post("/{devcontainer_id}/stop", response_model=DevcontainerView, status_code=202)
async def stop_devcontainer(devcontainer_id: str, request: Request) -> DevcontainerView:
    return await _dispatch_lifecycle(devcontainer_id, request, "stop", _STOP_ALLOWED_FROM)


async def _dispatch_lifecycle(
    devcontainer_id: str,
    request: Request,
    action: str,
    allowed_from: frozenset[DevcontainerStatus],
) -> DevcontainerView:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    view = await _view(resolved, request)
    if view.status not in allowed_from:
        raise InvalidDevcontainerStateError(action, view.status, allowed_from)
    service: DevcontainerService = request.app.state.devcontainer_service
    coro = (
        service.start(resolved.id, resolved.local_path)
        if action == "start"
        else service.stop(resolved.id, resolved.local_path)
    )
    run_in_background(coro)
    return view


async def _delete_impl(devcontainer_id: str, request: Request) -> Response:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    await request.app.state.devcontainer_cli.remove(resolved.local_path)
    live: LiveStateStore = request.app.state.live_state
    live.clear_transient(resolved.id)
    live.evict_harness(resolved.id)
    if resolved.source == DevcontainerSource.MANUAL:
        with get_connection() as conn:
            DevcontainerRepository(conn).delete(resolved.id)
            conn.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{devcontainer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_devcontainer(devcontainer_id: str, request: Request) -> Response:
    return await _delete_impl(devcontainer_id, request)


@router.post("/{devcontainer_id}/inject-runtime", status_code=202)
async def inject_runtime(devcontainer_id: str, request: Request) -> dict:
    resolved = request.app.state.catalog.get(devcontainer_id)
    if resolved is None:
        raise DevcontainerNotFoundError(devcontainer_id)
    injector = request.app.state.runtime_injector
    run_in_background(injector.inject_by_path(resolved.id, resolved.local_path))
    return {}
