import asyncio

from vibing_api.core.devcontainer_cli import DevcontainerFailure, DevcontainerSuccess
from vibing_api.core.devcontainer_service import DevcontainerService
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.vocabularies import DevcontainerStatus


class FakeAdapter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def start(self, local_path):
        self.calls.append(("start", local_path))
        return self.result

    async def stop(self, local_path):
        self.calls.append(("stop", local_path))
        return DevcontainerSuccess(operation="stop")


class FakeBroadcaster:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def test_start_sets_then_clears_transient_on_success() -> None:
    live = LiveStateStore()
    bc = FakeBroadcaster()
    svc = DevcontainerService(
        FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"})),
        live_state=live,
        broadcaster=bc,
    )
    asyncio.run(svc.start("dc1", "/path"))
    assert live.get_transient("dc1") is None  # cleared → live Docker truth
    assert [e.scope for e in bc.events] == ["devcontainers", "devcontainers"]


def test_start_failure_sets_error_transient() -> None:
    live = LiveStateStore()
    svc = DevcontainerService(
        FakeAdapter(
            DevcontainerFailure(
                operation="start", command=[], exit_code=1, stderr_tail="", message="boom"
            )
        ),
        live_state=live,
    )
    asyncio.run(svc.start("dc1", "/path"))
    assert live.get_transient("dc1") == DevcontainerStatus.ERROR


def test_stop_clears_transient_on_success() -> None:
    live = LiveStateStore()
    svc = DevcontainerService(FakeAdapter(DevcontainerSuccess(operation="start")), live_state=live)
    asyncio.run(svc.stop("dc1", "/path"))
    assert live.get_transient("dc1") is None
