from fastapi import APIRouter
from pydantic import BaseModel

from vibing_api.core.config import settings

router = APIRouter(tags=["config"])


class ConfigResponse(BaseModel):
    app_name: str
    api_v1_prefix: str


@router.get("/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    return ConfigResponse(
        app_name=settings.app_name,
        api_v1_prefix=settings.api_v1_prefix,
    )
