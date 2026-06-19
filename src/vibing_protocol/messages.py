"""Runtime-channel message envelopes.

Wire shapes exchanged over the single WebSocket connection between a runtime
and the Control Plane (ADR-0003). A `type` field discriminates each envelope.
"""

from typing import Literal

from pydantic import BaseModel

from .commands import Command


class RegisterEnvelope(BaseModel):
    """A runtime announcing itself on the channel."""

    type: Literal["runtime_registered"] = "runtime_registered"
    devcontainer_id: str | None = None


class CommandEnvelope(BaseModel):
    """A Command sent from the Control Plane to a runtime."""

    type: Literal["command"] = "command"
    command: Command


class HarnessStatusItem(BaseModel):
    name: str
    installed: bool
    authenticated: bool


class HarnessStatusEnvelope(BaseModel):
    type: Literal["harness_status"] = "harness_status"
    devcontainer_id: str
    items: list[HarnessStatusItem]
