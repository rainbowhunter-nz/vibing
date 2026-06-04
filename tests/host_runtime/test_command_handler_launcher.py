"""Tests for DevcontainerCommandHandler auto-launch integration (VIB-34)."""

import asyncio
from typing import Any

import pytest
from vibing_protocol import Command, RuntimeEvent

from vibing_host_runtime.command_handler import DevcontainerCommandHandler
from vibing_host_runtime.devcontainer_cli import (
    DevcontainerFailure,
    DevcontainerResult,
    DevcontainerSuccess,
)


class FakeAdapter:
    def __init__(self, result: DevcontainerResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    async def start(self, local_path: str) -> DevcontainerResult:
        self.calls.append(("start", local_path))
        return self._result

    async def stop(self, local_path: str) -> DevcontainerResult:
        self.calls.append(("stop", local_path))
        return self._result


class FakeLauncher:
    def __init__(self, raises: Exception | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []  # (devcontainer_id, container_id, local_path)
        self._raises = raises

    async def launch(self, devcontainer_id: str, container_id: str, local_path: str) -> None:
        self.calls.append((devcontainer_id, container_id, local_path))
        if self._raises is not None:
            raise self._raises


def _make_command(
    type_: str,
    devcontainer_id: str | None = "dc-1",
    payload: dict[str, Any] | None = None,
) -> Command:
    return Command(type=type_, devcontainer_id=devcontainer_id, payload=payload)  # type: ignore[arg-type]


def _run(
    handler: DevcontainerCommandHandler,
    command: Command,
) -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []

    async def emit(event: RuntimeEvent) -> None:
        events.append(event)

    asyncio.run(handler.handle(command, emit))
    return events


# --- AC2: launcher fires on start success ---


def test_start_success_fires_launcher() -> None:
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"}))
    launcher = FakeLauncher()
    handler = DevcontainerCommandHandler(adapter, launcher=launcher)
    events = _run(handler, _make_command("start_devcontainer", payload={"local_path": "/p"}))

    assert [e.event_type for e in events] == ["devcontainer_starting", "devcontainer_started"]
    assert launcher.calls == [("dc-1", "c1", "/p")]


def test_start_success_launcher_called_after_devcontainer_started_emitted() -> None:
    """Launcher fires AFTER devcontainer_started — events already emitted before launch."""
    events_at_launch: list[list[str]] = []
    emitted: list[RuntimeEvent] = []

    class TrackingLauncher:
        async def launch(self, devcontainer_id: str, container_id: str, local_path: str) -> None:
            events_at_launch.append([e.event_type for e in emitted])

    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"}))
    handler = DevcontainerCommandHandler(adapter, launcher=TrackingLauncher())  # type: ignore[arg-type]

    async def emit(event: RuntimeEvent) -> None:
        emitted.append(event)

    asyncio.run(
        handler.handle(_make_command("start_devcontainer", payload={"local_path": "/p"}), emit)
    )

    assert events_at_launch == [["devcontainer_starting", "devcontainer_started"]]


# --- AC3: launch failure leaves devcontainer_started intact ---


def test_start_success_launcher_nonzero_still_emits_started(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"}))

    class FailingLauncher:
        async def launch(self, devcontainer_id: str, container_id: str, local_path: str) -> None:
            import logzero

            logzero.logger.warning("agent launch failed: exit code 1")

    handler = DevcontainerCommandHandler(adapter, launcher=FailingLauncher())  # type: ignore[arg-type]
    events = _run(handler, _make_command("start_devcontainer", payload={"local_path": "/p"}))

    assert any(e.event_type == "devcontainer_started" for e in events)


def test_start_success_launcher_raises_still_emits_started() -> None:
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"}))

    class RaisingLauncher:
        async def launch(self, devcontainer_id: str, container_id: str, local_path: str) -> None:
            raise RuntimeError("unexpected crash")

    handler = DevcontainerCommandHandler(adapter, launcher=RaisingLauncher())  # type: ignore[arg-type]
    # Must not propagate — devcontainer_started should still be in events
    events = _run(handler, _make_command("start_devcontainer", payload={"local_path": "/p"}))
    assert any(e.event_type == "devcontainer_started" for e in events)


# --- Not-on-stop: launcher NOT fired on stop success ---


def test_stop_success_does_not_fire_launcher() -> None:
    adapter = FakeAdapter(DevcontainerSuccess(operation="stop", payload={}))
    launcher = FakeLauncher()
    handler = DevcontainerCommandHandler(adapter, launcher=launcher)
    events = _run(handler, _make_command("stop_devcontainer", payload={"local_path": "/p"}))

    assert [e.event_type for e in events] == ["devcontainer_stopping", "devcontainer_stopped"]
    assert launcher.calls == []


# --- AC3: start failure does not fire launcher ---


def test_start_failure_does_not_fire_launcher() -> None:
    failure = DevcontainerFailure(
        operation="start",
        command=["devcontainer", "up", "--workspace-folder", "/p"],
        exit_code=1,
        stderr_tail="",
        message="fail",
    )
    adapter = FakeAdapter(failure)
    launcher = FakeLauncher()
    handler = DevcontainerCommandHandler(adapter, launcher=launcher)
    _run(handler, _make_command("start_devcontainer", payload={"local_path": "/p"}))

    assert launcher.calls == []


# --- Module B: missing container_id → skip launch, devcontainer_started intact ---


def test_start_success_no_container_id_skips_launcher() -> None:
    """If container_id is absent from the up payload, launcher is not called."""
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={}))
    launcher = FakeLauncher()
    handler = DevcontainerCommandHandler(adapter, launcher=launcher)
    events = _run(handler, _make_command("start_devcontainer", payload={"local_path": "/p"}))

    assert any(e.event_type == "devcontainer_started" for e in events)
    assert launcher.calls == []


# --- Backward compat: handler without launcher still works ---


def test_handler_without_launcher_works() -> None:
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={}))
    handler = DevcontainerCommandHandler(adapter)  # no launcher
    events = _run(handler, _make_command("start_devcontainer", payload={"local_path": "/p"}))
    assert any(e.event_type == "devcontainer_started" for e in events)
