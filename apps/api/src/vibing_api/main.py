from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from vibing_api.api.routes import health
from vibing_api.core.config import settings
from vibing_api.core.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
