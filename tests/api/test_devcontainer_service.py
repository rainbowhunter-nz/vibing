import asyncio

from vibing_api.core.devcontainer_cli import DevcontainerSuccess, DevcontainerFailure
from vibing_api.core.devcontainer_service import DevcontainerService
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


class FakeInjector:
    def __init__(self):
        self.calls = []

    async def inject(self, devcontainer_id, container_id, local_path):
        self.calls.append((devcontainer_id, container_id, local_path))


class FakeRepo:
    def __init__(self):
        self.statuses = []

    def update(self, devcontainer_id, *, status):
        self.statuses.append((devcontainer_id, status))


class FakeBroadcaster:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def test_start_writes_starting_then_running_and_injects(monkeypatch):
    adapter = FakeAdapter(DevcontainerSuccess(operation="start", payload={"container_id": "c1"}))
    injector = FakeInjector()
    repo = FakeRepo()
    bc = FakeBroadcaster()
    svc = DevcontainerService(adapter, injector, broadcaster=bc, repo_factory=lambda: repo)

    asyncio.run(svc.start("dc1", "/path"))

    assert repo.statuses == [
        ("dc1", DevcontainerStatus.STARTING),
        ("dc1", DevcontainerStatus.RUNNING),
    ]
    assert injector.calls == [("dc1", "c1", "/path")]
    assert [e.scope for e in bc.events] == ["devcontainers", "devcontainers"]


def test_start_failure_writes_error_and_skips_injection():
    adapter = FakeAdapter(
        DevcontainerFailure(
            operation="start", command=[], exit_code=1, stderr_tail="boom", message="failed"
        )
    )
    injector = FakeInjector()
    repo = FakeRepo()
    svc = DevcontainerService(
        adapter, injector, broadcaster=FakeBroadcaster(), repo_factory=lambda: repo
    )

    asyncio.run(svc.start("dc1", "/path"))

    assert repo.statuses[-1] == ("dc1", DevcontainerStatus.ERROR)
    assert injector.calls == []
