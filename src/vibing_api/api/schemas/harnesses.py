from pydantic import BaseModel

from vibing_harness import HarnessStatus


class HarnessStatusItem(BaseModel):
    name: str
    installed: bool
    authenticated: bool

    @classmethod
    def from_status(cls, s: HarnessStatus) -> "HarnessStatusItem":
        return cls(name=s.name, installed=s.installed, authenticated=s.authenticated)


class HarnessStatusList(BaseModel):
    items: list[HarnessStatusItem]
    known: bool = False
