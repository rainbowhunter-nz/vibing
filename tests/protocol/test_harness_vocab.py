from vibing_protocol import Command, CommandType, HarnessStatusEnvelope, HarnessStatusItem


def test_authenticate_harness_command_type_wire_value():
    assert CommandType.AUTHENTICATE_HARNESS == "authenticate_harness"
    cmd = Command(
        type=CommandType.AUTHENTICATE_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex", "credentials": {"auth_json": {"OPENAI_API_KEY": "sk-x"}}},
    )
    assert cmd.payload is not None
    assert cmd.payload["harness"] == "codex"


def test_harness_status_envelope_round_trips():
    env = HarnessStatusEnvelope(
        devcontainer_id="dc-1",
        items=[
            HarnessStatusItem(name="codex", installed=True, authenticated=True),
            HarnessStatusItem(name="cursor", installed=False, authenticated=False),
        ],
    )
    assert env.type == "harness_status"
    dumped = env.model_dump()
    assert dumped["devcontainer_id"] == "dc-1"
    assert dumped["items"][0] == {"name": "codex", "installed": True, "authenticated": True}
    assert HarnessStatusEnvelope.model_validate(dumped) == env
