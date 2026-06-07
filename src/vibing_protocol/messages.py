"""Runtime-channel message envelopes.

Wire shapes exchanged over the single WebSocket connection between a runtime
(host or devcontainer) and the Control Plane (ADR-0003). A `type` field
discriminates each envelope. The runtime sends `runtime_registered` once to
announce itself, then `runtime_event` envelopes carrying RuntimeEvents.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .commands import Command
from .runtime_events import RuntimeEvent, RuntimeEventSource


class RegisterEnvelope(BaseModel):
    """A runtime announcing itself on the channel."""

    type: Literal["runtime_registered"] = "runtime_registered"
    source: RuntimeEventSource = RuntimeEventSource.HOST_RUNTIME_WORKER
    devcontainer_id: str | None = None


class RuntimeEventEnvelope(BaseModel):
    """A RuntimeEvent emitted by a runtime to the Control Plane."""

    type: Literal["runtime_event"] = "runtime_event"
    event: RuntimeEvent


class CommandEnvelope(BaseModel):
    """A Command sent from the Control Plane to a runtime."""

    type: Literal["command"] = "command"
    command: Command


class TextBlock(BaseModel):
    """Conversation text from one turn."""

    kind: Literal["text"] = "text"
    text: str


class ToolUseBlock(BaseModel):
    """A collapsed tool marker: tool name + short input summary (never the result)."""

    kind: Literal["tool_use"] = "tool_use"
    name: str
    summary: str


# Discriminated on `kind`; new block kinds (e.g. tool_result) extend the union without a wire break.
TranscriptBlock = Annotated[TextBlock | ToolUseBlock, Field(discriminator="kind")]


class TranscriptTurn(BaseModel):
    """One normalized conversation turn (ADR-0009): role + blocks + timestamp.

    `id` is Claude's per-message uuid (ADR-0010): the stable key the frontend reducer
    uses to reconcile live stream-deltas with the durable transcript. Empty when the
    source line carries no uuid (e.g. legacy fixtures).
    """

    id: str = ""
    role: Literal["user", "assistant"]
    blocks: list[TranscriptBlock]
    at: str


class TranscriptRequestEnvelope(BaseModel):
    """Control Plane -> agent: fetch a session's transcript, correlated by request_id."""

    type: Literal["transcript_request"] = "transcript_request"
    request_id: str
    agent_session_id: str


class TranscriptResponseEnvelope(BaseModel):
    """Agent -> Control Plane: the normalized transcript, correlated to the request_id."""

    type: Literal["transcript_response"] = "transcript_response"
    request_id: str
    turns: list[TranscriptTurn]


class RunStartedDelta(BaseModel):
    """Run boundary: a fresh Claude invocation began (ADR-0010, text-only slice)."""

    kind: Literal["run_started"] = "run_started"


class TextDelta(BaseModel):
    """Append `text` to the assistant turn keyed by `turn_id` (ADR-0010)."""

    kind: Literal["text"] = "text"
    turn_id: str
    role: Literal["assistant"] = "assistant"
    text: str


class RunEndedDelta(BaseModel):
    """Run boundary: the terminal result event fired; the browser reconciles to transcript."""

    kind: Literal["run_ended"] = "run_ended"


# Discriminated on `kind`; tool-call deltas (VIB-110) extend this union without a wire break.
TurnDelta = Annotated[RunStartedDelta | TextDelta | RunEndedDelta, Field(discriminator="kind")]


class TurnDeltaEnvelope(BaseModel):
    """Agent -> Control Plane: one live turn-delta for an active session (ADR-0010).

    Relayed to subscribed browsers over the per-session SSE stream. Ephemeral — never
    persisted; the durable transcript stays the source of truth.
    """

    type: Literal["turn_delta"] = "turn_delta"
    devcontainer_id: str
    agent_session_id: str
    delta: TurnDelta
