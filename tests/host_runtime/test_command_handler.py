"""Tests for DevcontainerCommandHandler — fake adapter, no real CLI/Docker."""

import asyncio
from typing import Any

from vibing_protocol import Command, RuntimeEvent

from vibing_host_runtime.command_handler import DevcontainerCommandHandler
from vibing_host_runtime.devcontainer_cli import (
    DevcontainerFailure,
    DevcontainerResult,
    DevcontainerSuccess,
)


class FakeAdapter:
    """Records calls; result and the events-list snapshot at call time are caller-controlled."""

    def __init__(self, result: DevcontainerResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []  # (method, local_path)
        self.events_len_at_call: list[int] = []
        self._events: list[RuntimeEvent] = []  # set by test before running

    async def start(self, local_path: str) -> DevcontainerResult:
        self.calls.append(("start", local_path))
        self.events_len_at_call.append(len(self._events))
        return self._result

    async def stop(self, local_path: str) -> DevcontainerResult:
        self.calls.append(("stop", local_path))
        self.events_len_at_call.append(len(self._events))
        return self._result


def _make_command(
    type_: str,
    devcontainer_id: str | None = "dc-1",
    payload: dict[str, Any] | None = None,
) -> Command:
    return Command(type=type_, devcontainer_id=devcontainer_id, payload=payload)  # type: ignore[arg-type]


def _run(
    adapter: FakeAdapter,
    handler: DevcontainerCommandHandler,
    command: Command,
    events: list[RuntimeEvent],
) -> None:
    adapter._events = events  # share the list so ordering is observable

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    asyncio.run(handler.handle(command, emit))


# --- AC1: pre-event before adapter on start ---


def test_start_emits_starting_before_adapter_invocation() -> None:
    """AC1: devcontainer_starting emitted before adapter.start is called."""
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"}))
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(
        adapter, handler, _make_command("start_devcontainer", payload={"local_path": "/p"}), events
    )

    assert adapter.events_len_at_call == [1]
    assert events[0].event_type == "devcontainer_starting"


# --- AC2 & AC9: full start sequence ---


def test_start_success_full_event_sequence() -> None:
    """AC2 & AC9: successful start → [devcontainer_starting, devcontainer_started] with adapter payload."""
    success_payload = {"container_id": "abc", "remote_user": "vscode"}
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload=success_payload))
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(
        adapter, handler, _make_command("start_devcontainer", payload={"local_path": "/p"}), events
    )

    assert [e.event_type for e in events] == ["devcontainer_starting", "devcontainer_started"]
    assert events[1].payload == success_payload
    for e in events:
        assert e.source == "host_runtime_worker"
        assert e.devcontainer_id == "dc-1"


# --- AC3: failed start ---


def test_start_failure_emits_devcontainer_failed() -> None:
    """AC3: DevcontainerFailure on start → devcontainer_failed with bounded details."""
    failure = DevcontainerFailure(
        operation="start",
        command=["devcontainer", "up", "--workspace-folder", "/p"],
        exit_code=1,
        stderr_tail="error output",
        message="devcontainer start failed with exit code 1",
    )
    adapter = FakeAdapter(failure)
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(
        adapter, handler, _make_command("start_devcontainer", payload={"local_path": "/p"}), events
    )

    assert events[-1].event_type == "devcontainer_failed"
    p = events[-1].payload
    assert p is not None
    assert p["operation"] == "start"
    assert "command" in p and "exit_code" in p and "stderr_tail" in p and "message" in p
    for e in events:
        assert e.source == "host_runtime_worker"
        assert e.devcontainer_id == "dc-1"


# --- AC4: pre-event before adapter on stop ---


def test_stop_emits_stopping_before_adapter_invocation() -> None:
    """AC4: devcontainer_stopping emitted before adapter.stop is called."""
    adapter = FakeAdapter(DevcontainerSuccess(operation="stop", payload={}))
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(adapter, handler, _make_command("stop_devcontainer", payload={"local_path": "/p"}), events)

    assert adapter.events_len_at_call == [1]
    assert events[0].event_type == "devcontainer_stopping"


# --- AC5: successful stop ---


def test_stop_success_emits_stopped_no_payload() -> None:
    """AC5: successful stop → [devcontainer_stopping, devcontainer_stopped] with no payload."""
    adapter = FakeAdapter(DevcontainerSuccess(operation="stop", payload={}))
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(adapter, handler, _make_command("stop_devcontainer", payload={"local_path": "/p"}), events)

    assert [e.event_type for e in events] == ["devcontainer_stopping", "devcontainer_stopped"]
    assert events[1].payload is None
    for e in events:
        assert e.source == "host_runtime_worker"
        assert e.devcontainer_id == "dc-1"


# --- AC6: failed stop ---


def test_stop_failure_emits_devcontainer_failed() -> None:
    """AC6: DevcontainerFailure on stop → devcontainer_failed with bounded details."""
    failure = DevcontainerFailure(
        operation="stop",
        command=["devcontainer", "stop", "--workspace-folder", "/p"],
        exit_code=2,
        stderr_tail="stop error",
        message="devcontainer stop failed with exit code 2",
    )
    adapter = FakeAdapter(failure)
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(adapter, handler, _make_command("stop_devcontainer", payload={"local_path": "/p"}), events)

    assert events[-1].event_type == "devcontainer_failed"
    p = events[-1].payload
    assert p is not None
    assert p["operation"] == "stop"
    assert "command" in p and "exit_code" in p and "stderr_tail" in p and "message" in p
    for e in events:
        assert e.source == "host_runtime_worker"


# --- AC7: missing local_path with devcontainer_id ---


def test_start_missing_local_path_with_devcontainer_id_emits_failed() -> None:
    """AC7 (start): missing local_path + devcontainer_id → exactly one devcontainer_failed, no adapter call."""
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={}))
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(
        adapter,
        handler,
        _make_command("start_devcontainer", devcontainer_id="dc-x", payload={}),
        events,
    )

    assert len(events) == 1
    assert events[0].event_type == "devcontainer_failed"
    assert events[0].devcontainer_id == "dc-x"
    assert adapter.calls == []


def test_stop_missing_local_path_with_devcontainer_id_emits_failed() -> None:
    """AC7 (stop): missing local_path + devcontainer_id → exactly one devcontainer_failed, no adapter call."""
    adapter = FakeAdapter(DevcontainerSuccess(operation="stop", payload={}))
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(
        adapter,
        handler,
        _make_command("stop_devcontainer", devcontainer_id="dc-y", payload=None),
        events,
    )

    assert len(events) == 1
    assert events[0].event_type == "devcontainer_failed"
    assert events[0].devcontainer_id == "dc-y"
    assert adapter.calls == []


# --- AC8: unsupported command ---


def test_unsupported_command_emits_no_events_and_skips_adapter() -> None:
    """AC8: unsupported command type → no events, adapter not called."""
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={}))
    handler = DevcontainerCommandHandler(adapter)
    events: list[RuntimeEvent] = []
    _run(
        adapter, handler, _make_command("start_agent_session", payload={"local_path": "/p"}), events
    )

    assert events == []
    assert adapter.calls == []
