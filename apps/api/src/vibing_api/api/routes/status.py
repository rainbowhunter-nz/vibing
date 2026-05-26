from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from pydantic import BaseModel

from vibing_api.core.config import settings

router = APIRouter(tags=["status"])


def _service_version() -> str:
    try:
        return version("vibing-api")
    except PackageNotFoundError:
        return "0.0.0"


class StatusResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    return StatusResponse(status="ok", service=settings.app_name, version=_service_version())
