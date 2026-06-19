"""Pure conversion of Claude `--output-format stream-json` lines into turn-deltas.

The ONLY new place pinned to Claude's stream-json wire format (ADR-0010), mirroring
the role transcript.py plays for the on-disk JSONL. Emits text and tool_use deltas.
Malformed and unknown lines are skipped defensively.

Wire shapes consumed (one JSON object per stdout line):
- {"type":"system","subtype":"init",...}                          -> run_started
- {"type":"stream_event","event":{"type":"message_start","message":{"id",...}}}
- {"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text"}}}
- {"type":"stream_event","event":{"type":"content_block_start","content_block":{"type":"tool_use","name","input"}}}
- {"type":"assistant","uuid","message":{"id","content":[...]}}    -> text+tool deltas in order (if not streamed)
- {"type":"result","subtype","is_error","result"}                 -> terminal + run_ended

Turn id (ADR-0010): partial text/tool inherits the id from the preceding message_start;
the complete `assistant` event uses its top-level uuid, falling back to message.id.
"""

import json
from dataclasses import dataclass, field

from vibing_protocol import RunEndedDelta, RunStartedDelta, TextDelta, ToolUseDelta, TurnDelta

from .content_blocks import ContentItem, TextItem, ToolItem, item_from_block, parse_content


@dataclass(frozen=True)
class TerminalResult:
    """The `result` event's outcome — drives session_completed/session_failed mapping."""

    result_text: str
    is_error: bool


@dataclass(frozen=True)
class NormalizedLine:
    deltas: list[TurnDelta] = field(default_factory=list)
    terminal: TerminalResult | None = None


def _to_delta(turn_id: str, item: ContentItem) -> TurnDelta:
    if isinstance(item, TextItem):
        return TextDelta(turn_id=turn_id, text=item.text)
    return ToolUseDelta(turn_id=turn_id, name=item.name, summary=item.summary)


def _deltas_from_content(turn_id: str, content: object) -> list[TurnDelta]:
    """Project content items onto turn-deltas, in arrival order."""
    return [_to_delta(turn_id, item) for item in parse_content(content)]


class StreamNormalizer:
    """Stateful per-run normalizer: tracks the current message id across partials.

    One instance per Claude invocation. `feed(line)` returns the deltas (and any
    terminal result) for that line; state is the in-flight message id and whether
    partial text was streamed (so the complete `assistant` event isn't double-emitted).
    """

    def __init__(self) -> None:
        self._current_message_id = ""
        self._streamed_partials = False

    def feed(self, line: str) -> NormalizedLine:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return NormalizedLine()
        if not isinstance(obj, dict):
            return NormalizedLine()

        msg_type = obj.get("type")
        if msg_type == "system" and obj.get("subtype") == "init":
            return NormalizedLine(deltas=[RunStartedDelta()])
        if msg_type == "stream_event":
            return self._from_stream_event(obj.get("event"))
        if msg_type == "assistant":
            return self._from_complete_assistant(obj)
        if msg_type == "result":
            result = obj.get("result")
            return NormalizedLine(
                deltas=[RunEndedDelta()],
                terminal=TerminalResult(
                    result_text=result if isinstance(result, str) else "",
                    is_error=bool(obj.get("is_error")),
                ),
            )
        return NormalizedLine()

    def _from_stream_event(self, event: object) -> NormalizedLine:
        if not isinstance(event, dict):
            return NormalizedLine()
        event_type = event.get("type")
        if event_type == "message_start":
            message = event.get("message")
            if isinstance(message, dict) and isinstance(message.get("id"), str):
                self._current_message_id = message["id"]
            return NormalizedLine()
        if event_type == "content_block_delta":
            delta = event.get("delta")
            if (
                isinstance(delta, dict)
                and delta.get("type") == "text_delta"
                and isinstance(delta.get("text"), str)
            ):
                self._streamed_partials = True
                return NormalizedLine(
                    deltas=[TextDelta(turn_id=self._current_message_id, text=delta["text"])]
                )
        if event_type == "content_block_start":
            item = item_from_block(event.get("content_block"))
            if isinstance(item, ToolItem):
                self._streamed_partials = True
                return NormalizedLine(deltas=[_to_delta(self._current_message_id, item)])
        return NormalizedLine()

    def _from_complete_assistant(self, obj: dict) -> NormalizedLine:
        # Partials already streamed this content block-by-block; don't re-emit it.
        if self._streamed_partials:
            return NormalizedLine()
        message = obj.get("message")
        if not isinstance(message, dict):
            return NormalizedLine()
        uuid = obj.get("uuid")
        msg_id = message.get("id")
        if isinstance(uuid, str) and uuid:
            turn_id = uuid
        elif isinstance(msg_id, str):
            turn_id = msg_id
        else:
            turn_id = ""
        deltas = _deltas_from_content(turn_id, message.get("content"))
        return NormalizedLine(deltas=deltas) if deltas else NormalizedLine()
