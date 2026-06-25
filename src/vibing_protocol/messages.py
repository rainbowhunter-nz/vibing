"""Runtime-channel message envelopes.

Wire shapes exchanged over the single WebSocket connection between a runtime
and the Control Plane (ADR-0003). A `type` field discriminates each envelope.
"""

from typing import Literal

from pydantic import BaseModel


class RegisterEnvelope(BaseModel):
    """A runtime announcing itself on the channel."""

    type: Literal["runtime_registered"] = "runtime_registered"
    devcontainer_id: str | None = None


class DelegatedRunItem(BaseModel):
    run_id: str
    harness: str
    model: str
    title: str
    status: str
    result: str | None = None
    error: dict | None = None
    started_at: str


class DelegatedRunsEnvelope(BaseModel):
    type: Literal["delegated_runs"] = "delegated_runs"
    devcontainer_id: str
    items: list[DelegatedRunItem]
