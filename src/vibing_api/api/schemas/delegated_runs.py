from pydantic import BaseModel


class DelegatedRunItem(BaseModel):
    run_id: str
    harness: str
    model: str
    title: str
    status: str
    result: str | None = None
    error: dict | None = None
    started_at: str


class DelegatedRunList(BaseModel):
    items: list[DelegatedRunItem]
