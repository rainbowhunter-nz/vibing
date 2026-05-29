from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from vibing_api.api.routes import (
    config,
    devcontainers,
    diagnostics,
    health,
    settings as settings_route,
    status,
)
from vibing_api.core.config import settings
from vibing_api.core.database import init_db
from vibing_api.core.errors import register_error_handlers


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
    register_error_handlers(app)
    for router in (
        health.router,
        status.router,
        config.router,
        devcontainers.router,
        settings_route.router,
        diagnostics.router,
    ):
        app.include_router(router, prefix=settings.api_v1_prefix)
    if settings.static_dir:
        app.mount("/", SpaStaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


app = create_app()
