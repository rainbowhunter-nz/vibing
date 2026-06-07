"""Tests for the Claude stream-json -> turn-delta normalizer (VIB-109, ADR-0010).

The normalizer is the ONLY new place pinned to Claude's stream-json wire format
(mirrors transcript.py). Text-only slice: partial text, completed text, terminal
result, malformed/unknown lines, and turn-id propagation.
"""

import json

from vibing_protocol import RunEndedDelta, RunStartedDelta, TextDelta

from vibing_devcontainer_runtime.stream_normalizer import StreamNormalizer, TerminalResult


def _line(obj: object) -> str:
    return json.dumps(obj)


def test_init_event_emits_run_started() -> None:
    n = StreamNormalizer()
    out = n.feed(_line({"type": "system", "subtype": "init", "session_id": "s"}))
    assert out.deltas == [RunStartedDelta()]
    assert out.terminal is None


def test_partial_text_delta_keyed_by_message_id() -> None:
    n = StreamNormalizer()
    # message_start carries the message id; subsequent text_deltas inherit it.
    n.feed(
        _line(
            {
                "type": "stream_event",
                "event": {"type": "message_start", "message": {"id": "msg_1", "role": "assistant"}},
            }
        )
    )
    out = n.feed(
        _line(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Hel"},
                },
            }
        )
    )
    assert out.deltas == [TextDelta(turn_id="msg_1", text="Hel")]
    out2 = n.feed(
        _line(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "lo"},
                },
            }
        )
    )
    assert out2.deltas == [TextDelta(turn_id="msg_1", text="lo")]


def test_completed_assistant_text_when_no_partials_seen() -> None:
    """If partials were off, the complete assistant message yields the full text once."""
    n = StreamNormalizer()
    out = n.feed(
        _line(
            {
                "type": "assistant",
                "uuid": "u-9",
                "message": {
                    "id": "msg_2",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Done."}],
                },
            }
        )
    )
    assert out.deltas == [TextDelta(turn_id="u-9", text="Done.")]


def test_completed_assistant_is_suppressed_when_partials_streamed_it() -> None:
    """Avoid double-counting: text already streamed as partials is not re-emitted."""
    n = StreamNormalizer()
    n.feed(
        _line(
            {
                "type": "stream_event",
                "event": {"type": "message_start", "message": {"id": "msg_3", "role": "assistant"}},
            }
        )
    )
    n.feed(
        _line(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Hi"},
                },
            }
        )
    )
    out = n.feed(
        _line(
            {
                "type": "assistant",
                "uuid": "u-3",
                "message": {
                    "id": "msg_3",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hi"}],
                },
            }
        )
    )
    assert out.deltas == []


def test_tool_use_block_is_not_streamed_as_a_delta() -> None:
    """Tool-call cards are VIB-110; text-only here. tool_use blocks produce no delta."""
    n = StreamNormalizer()
    out = n.feed(
        _line(
            {
                "type": "assistant",
                "uuid": "u-4",
                "message": {
                    "id": "msg_4",
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}}],
                },
            }
        )
    )
    assert out.deltas == []


def test_terminal_result_success() -> None:
    n = StreamNormalizer()
    out = n.feed(
        _line(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "All done",
            }
        )
    )
    assert out.terminal == TerminalResult(result_text="All done", is_error=False)
    assert out.deltas == [RunEndedDelta()]


def test_terminal_result_error() -> None:
    n = StreamNormalizer()
    out = n.feed(_line({"type": "result", "subtype": "error_during_execution", "is_error": True}))
    assert out.terminal == TerminalResult(result_text="", is_error=True)
    assert out.deltas == [RunEndedDelta()]


def test_malformed_line_is_ignored() -> None:
    n = StreamNormalizer()
    out = n.feed("not json at all")
    assert out.deltas == []
    assert out.terminal is None


def test_unknown_line_type_is_ignored() -> None:
    n = StreamNormalizer()
    out = n.feed(_line({"type": "user", "message": {"role": "user", "content": "hi"}}))
    assert out.deltas == []
    assert out.terminal is None


def test_partial_text_without_message_start_uses_empty_id() -> None:
    """Defensive: a text_delta before any message_start still surfaces (empty id)."""
    n = StreamNormalizer()
    out = n.feed(
        _line(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "x"},
                },
            }
        )
    )
    assert out.deltas == [TextDelta(turn_id="", text="x")]
