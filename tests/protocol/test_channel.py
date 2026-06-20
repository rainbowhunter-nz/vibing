from vibing_protocol import Command, CommandEnvelope, CommandType, RegisterEnvelope, decode, encode


def test_decode_returns_dict_for_json_object():
    assert decode('{"type": "command"}') == {"type": "command"}


def test_decode_returns_none_for_invalid_json():
    assert decode("not json") is None


def test_decode_returns_none_for_non_object_json():
    assert decode("[1, 2, 3]") is None


def test_encode_then_decode_round_trips_register_envelope():
    envelope = RegisterEnvelope(devcontainer_id="dc-1")
    restored = decode(encode(envelope))
    assert restored is not None
    assert RegisterEnvelope.model_validate(restored) == envelope


def test_encode_then_decode_round_trips_command_envelope():
    envelope = CommandEnvelope(
        command=Command(
            type=CommandType.AUTHENTICATE_HARNESS,
            devcontainer_id="dc-1",
            payload={"harness": "codex"},
        )
    )
    restored = decode(encode(envelope))
    assert restored is not None
    assert CommandEnvelope.model_validate(restored) == envelope
