from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vibing_api.api.routes import config, health, status, workspaces
from vibing_api.core.config import settings
from vibing_api.core.database import init_db
from vibing_api.core.errors import register_error_handlers


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_error_handlers(app)
    for router in (health.router, status.router, config.router, workspaces.router):
        app.include_router(router, prefix=settings.api_v1_prefix)
    if settings.static_dir:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    return app


app = create_app()
