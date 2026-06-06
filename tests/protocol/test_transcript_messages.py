"""Tests for transcript request/reply envelopes and normalized turn models."""

from vibing_protocol import (
    TextBlock,
    TranscriptRequestEnvelope,
    TranscriptResponseEnvelope,
    TranscriptTurn,
    ToolUseBlock,
)


def test_request_envelope_round_trips() -> None:
    env = TranscriptRequestEnvelope(request_id="req-1", agent_session_id="sess-1")
    assert env.type == "transcript_request"
    dumped = env.model_dump()
    assert dumped == {
        "type": "transcript_request",
        "request_id": "req-1",
        "agent_session_id": "sess-1",
    }
    assert TranscriptRequestEnvelope.model_validate(dumped) == env


def test_response_envelope_round_trips() -> None:
    turn = TranscriptTurn(
        role="assistant",
        blocks=[
            TextBlock(text="hi"),
            ToolUseBlock(name="Bash", summary="ls -la"),
        ],
        at="2026-06-06T00:00:00Z",
    )
    env = TranscriptResponseEnvelope(request_id="req-1", turns=[turn])
    assert env.type == "transcript_response"
    dumped = env.model_dump()
    assert dumped["type"] == "transcript_response"
    assert dumped["turns"][0]["role"] == "assistant"
    assert dumped["turns"][0]["blocks"][0] == {"kind": "text", "text": "hi"}
    assert dumped["turns"][0]["blocks"][1] == {
        "kind": "tool_use",
        "name": "Bash",
        "summary": "ls -la",
    }
    assert TranscriptResponseEnvelope.model_validate(dumped) == env


def test_blocks_are_discriminated_on_kind() -> None:
    turn = TranscriptTurn.model_validate(
        {
            "role": "user",
            "blocks": [{"kind": "text", "text": "hello"}],
            "at": "2026-06-06T00:00:00Z",
        }
    )
    assert isinstance(turn.blocks[0], TextBlock)
    assert turn.blocks[0].kind == "text"
