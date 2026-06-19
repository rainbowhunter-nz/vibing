from pydantic import BaseModel


class HarnessStatusItem(BaseModel):
    name: str
    installed: bool
    authenticated: bool


class HarnessStatusList(BaseModel):
    items: list[HarnessStatusItem]
