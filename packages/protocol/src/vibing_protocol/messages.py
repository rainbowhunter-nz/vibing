"""Runtime-channel message envelopes.

Wire shapes exchanged over the single WebSocket connection between a runtime
(host or devcontainer) and the Control Plane (ADR-0003). A `type` field
discriminates each envelope. The runtime sends `runtime_registered` once to
announce itself, then `runtime_event` envelopes carrying RuntimeEvents.
"""

from typing import Literal

from pydantic import BaseModel

from .runtime_events import RuntimeEvent, RuntimeEventSource


class RegisterEnvelope(BaseModel):
    """A runtime announcing itself on the channel."""

    type: Literal["runtime_registered"] = "runtime_registered"
    source: RuntimeEventSource = "host_runtime_worker"


class RuntimeEventEnvelope(BaseModel):
    """A RuntimeEvent emitted by a runtime to the Control Plane."""

    type: Literal["runtime_event"] = "runtime_event"
    event: RuntimeEvent
