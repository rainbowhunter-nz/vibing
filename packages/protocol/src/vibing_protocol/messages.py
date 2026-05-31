"""Runtime-channel message envelopes.

Wire shapes exchanged over the single WebSocket connection between a runtime
(host or devcontainer) and the Control Plane (ADR-0003). A `type` field
discriminates each envelope. The runtime sends `runtime_registered` once to
announce itself, then `runtime_event` envelopes carrying RuntimeEvents.
"""

from typing import Literal

from pydantic import BaseModel

from .commands import Command
from .runtime_events import RuntimeEvent, RuntimeEventSource


class RegisterEnvelope(BaseModel):
    """A runtime announcing itself on the channel."""

    type: Literal["runtime_registered"] = "runtime_registered"
    source: RuntimeEventSource = "host_runtime_worker"
    devcontainer_id: str | None = None


class RuntimeEventEnvelope(BaseModel):
    """A RuntimeEvent emitted by a runtime to the Control Plane."""

    type: Literal["runtime_event"] = "runtime_event"
    event: RuntimeEvent


class CommandEnvelope(BaseModel):
    """A Command sent from the Control Plane to a runtime."""

    type: Literal["command"] = "command"
    command: Command
