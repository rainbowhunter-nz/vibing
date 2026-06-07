"""Tests for the Claude stream-json -> turn-delta normalizer (VIB-109/110, ADR-0010).

The normalizer is the ONLY new place pinned to Claude's stream-json wire format
(mirrors transcript.py). Covers: partial text, tool_use cards, completed content
blocks in arrival order, terminal result, malformed/unknown lines, turn-id propagation.
"""

import json

from vibing_protocol import RunEndedDelta, RunStartedDelta, TextDelta, ToolUseDelta

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


def test_tool_use_block_in_complete_assistant_emits_tool_use_delta() -> None:
    """Complete assistant with a tool_use block yields a ToolUseDelta (VIB-110)."""
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
    assert out.deltas == [ToolUseDelta(turn_id="u-4", name="Bash", summary="cmd=ls")]


def test_streaming_tool_use_via_content_block_start() -> None:
    """A content_block_start with type=tool_use emits a ToolUseDelta (VIB-110 live path)."""
    n = StreamNormalizer()
    n.feed(
        _line(
            {"type": "stream_event", "event": {"type": "message_start", "message": {"id": "msg_5"}}}
        )
    )
    out = n.feed(
        _line(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"path": "/a/b"},
                    },
                },
            }
        )
    )
    assert out.deltas == [ToolUseDelta(turn_id="msg_5", name="Read", summary="path=/a/b")]


def test_complete_assistant_text_and_tool_interleaved_in_order() -> None:
    """Mixed text+tool content blocks emit deltas in arrival order (VIB-110 AC2)."""
    n = StreamNormalizer()
    out = n.feed(
        _line(
            {
                "type": "assistant",
                "uuid": "u-6",
                "message": {
                    "id": "msg_6",
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Let me check."},
                        {"type": "tool_use", "name": "Bash", "input": {"cmd": "pwd"}},
                        {"type": "text", "text": "Done."},
                    ],
                },
            }
        )
    )
    assert out.deltas == [
        TextDelta(turn_id="u-6", text="Let me check."),
        ToolUseDelta(turn_id="u-6", name="Bash", summary="cmd=pwd"),
        TextDelta(turn_id="u-6", text="Done."),
    ]


def test_streaming_tool_use_suppresses_complete_assistant_re_emit() -> None:
    """A tool_use via content_block_start sets streamed_partials=True -> assistant not re-emitted."""
    n = StreamNormalizer()
    n.feed(
        _line(
            {"type": "stream_event", "event": {"type": "message_start", "message": {"id": "msg_7"}}}
        )
    )
    n.feed(
        _line(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}},
                },
            }
        )
    )
    # Complete assistant arrived — should be suppressed since partials were streamed
    out = n.feed(
        _line(
            {
                "type": "assistant",
                "uuid": "u-7",
                "message": {
                    "id": "msg_7",
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
