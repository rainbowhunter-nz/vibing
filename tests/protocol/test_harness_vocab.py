from vibing_protocol import Command, CommandType, EventType, RuntimeEvent, RuntimeEventSource


def test_authenticate_harness_command_type_wire_value():
    assert CommandType.AUTHENTICATE_HARNESS == "authenticate_harness"
    cmd = Command(
        type=CommandType.AUTHENTICATE_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex", "credentials": {"auth_json": {"OPENAI_API_KEY": "sk-x"}}},
    )
    assert cmd.payload is not None
    assert cmd.payload["harness"] == "codex"


def test_delegated_run_and_harness_status_event_types():
    assert EventType.HARNESS_STATUS == "harness_status"
    assert EventType.DELEGATED_RUN_STARTED == "delegated_run_started"
    assert EventType.DELEGATED_RUN_COMPLETED == "delegated_run_completed"
    assert EventType.DELEGATED_RUN_FAILED == "delegated_run_failed"
    evt = RuntimeEvent(
        event_type=EventType.DELEGATED_RUN_COMPLETED,
        source=RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT,
        devcontainer_id="dc-1",
        payload={"delegated_run_id": "run-1", "result": "done"},
    )
    assert evt.payload is not None and evt.payload["delegated_run_id"] == "run-1"
