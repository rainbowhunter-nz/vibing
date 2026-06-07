"""Tests for transcript request/reply envelopes and normalized turn models."""

from vibing_protocol import (
    RunEndedDelta,
    RunStartedDelta,
    TextBlock,
    TextDelta,
    TranscriptRequestEnvelope,
    TranscriptResponseEnvelope,
    TranscriptTurn,
    ToolUseBlock,
    TurnDeltaEnvelope,
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


def test_turn_id_defaults_empty_and_round_trips() -> None:
    # Legacy lines without a uuid still validate (id defaults to "").
    turn = TranscriptTurn.model_validate(
        {"role": "user", "blocks": [{"kind": "text", "text": "x"}], "at": "t"}
    )
    assert turn.id == ""

    with_id = TranscriptTurn(id="u-1", role="assistant", blocks=[TextBlock(text="hi")], at="t")
    assert with_id.model_dump()["id"] == "u-1"


def test_turn_delta_text_envelope_round_trips() -> None:
    env = TurnDeltaEnvelope(
        devcontainer_id="dc-1",
        agent_session_id="sess-1",
        delta=TextDelta(turn_id="u-1", text="Hel"),
    )
    assert env.type == "turn_delta"
    dumped = env.model_dump()
    assert dumped["delta"] == {"kind": "text", "turn_id": "u-1", "role": "assistant", "text": "Hel"}
    assert TurnDeltaEnvelope.model_validate(dumped) == env


def test_turn_delta_run_boundaries_round_trip() -> None:
    start = TurnDeltaEnvelope(devcontainer_id="dc-1", agent_session_id="s", delta=RunStartedDelta())
    end = TurnDeltaEnvelope(devcontainer_id="dc-1", agent_session_id="s", delta=RunEndedDelta())
    assert start.model_dump()["delta"] == {"kind": "run_started"}
    assert end.model_dump()["delta"] == {"kind": "run_ended"}
    assert TurnDeltaEnvelope.model_validate(start.model_dump()).delta.kind == "run_started"
    assert TurnDeltaEnvelope.model_validate(end.model_dump()).delta.kind == "run_ended"
