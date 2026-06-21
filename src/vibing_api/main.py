from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from vibing_api.api.routes import (
    config,
    delegated_runs,
    devcontainers,
    diagnostics,
    events,
    harnesses,
    health,
    runtime,
    settings as settings_route,
    status,
)
from vibing_api.core.broadcaster import Broadcaster
from vibing_api.core.catalog import DevcontainerCatalog
from vibing_api.core.config import settings
from vibing_api.core.database import get_connection, init_db
from vibing_api.core.devcontainer_cli import DevcontainerCliAdapter
from vibing_api.core.devcontainer_service import DevcontainerService
from vibing_api.core.discovery import scan
from vibing_api.core.errors import register_error_handlers
from vibing_api.core.file_config import load_devcontainers_dir
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.core.runtime_injector import RuntimeInjector
from vibing_api.repositories.devcontainers import DevcontainerRepository


class SpaStaticFiles(StaticFiles):
    """Serve index.html for unmatched client-side routes (e.g. /devcontainers on refresh)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            # Keep API and asset 404s as real 404s; only fall back for SPA routes.
            last = path.rsplit("/", 1)[-1]
            if path.startswith("api/") or "." in last:
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.runtime_manager = RuntimeRegistry()
    app.state.broadcaster = Broadcaster()
    app.state.live_state = LiveStateStore()
    app.state.devcontainer_cli = DevcontainerCliAdapter()
    app.state.runtime_injector = RuntimeInjector()

    def _list_records():
        with get_connection() as conn:
            return DevcontainerRepository(conn).list()

    def _get_record(devcontainer_id: str):
        with get_connection() as conn:
            return DevcontainerRepository(conn).get(devcontainer_id)

    app.state.catalog = DevcontainerCatalog(
        list_records=_list_records,
        get_record=_get_record,
        scanner=lambda: scan(load_devcontainers_dir()),
    )
    app.state.devcontainer_service = DevcontainerService(
        app.state.devcontainer_cli,
        live_state=app.state.live_state,
        broadcaster=app.state.broadcaster,
    )
    register_error_handlers(app)
    for router in (
        health.router,
        status.router,
        config.router,
        devcontainers.router,
        harnesses.router,
        delegated_runs.router,
        settings_route.router,
        diagnostics.router,
        runtime.router,
        events.router,
    ):
        app.include_router(router, prefix=settings.api_v1_prefix)
    if settings.static_dir:
        app.mount("/", SpaStaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


app = create_app()
