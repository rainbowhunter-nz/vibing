import asyncio

from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.core.runtime_service import RuntimeService
from vibing_api.core.vocabularies import RuntimeState


class FakeInjector:
    def __init__(self, inject_ok: bool = True) -> None:
        self.inject_ok = inject_ok
        self.stopped: list[str] = []
        self.log = "log contents"

    async def inject_by_path(self, devcontainer_id: str, local_path: str) -> bool:
        return self.inject_ok

    async def stop_runtime(self, local_path: str) -> bool:
        self.stopped.append(local_path)
        return True

    def stream_log(self, local_path: str):
        async def gen():
            yield b"chunk1 "
            yield b"chunk2"

        return gen()


class FakeConn:
    async def send(self, command) -> None: ...


def _service(injector, registry=None, timeout=30.0):
    return RuntimeService(
        injector,
        live_state=LiveStateStore(),
        registry=registry or RuntimeRegistry(),
        broadcaster=None,
        launch_timeout=timeout,
    )


def test_inject_sets_launching_transient() -> None:
    svc = _service(FakeInjector(inject_ok=True), timeout=999)
    asyncio.run(svc.inject("dc1", "/work/repo"))
    assert svc._live.get_runtime_transient("dc1") == RuntimeState.LAUNCHING


def test_inject_failure_clears_to_disconnected() -> None:
    svc = _service(FakeInjector(inject_ok=False))
    asyncio.run(svc.inject("dc1", "/work/repo"))
    assert svc._live.get_runtime_transient("dc1") is None


def test_expire_launching_clears_when_not_connected() -> None:
    svc = _service(FakeInjector(), timeout=0)
    svc._live.set_runtime_transient("dc1", RuntimeState.LAUNCHING)
    asyncio.run(svc._expire_launching("dc1"))
    assert svc._live.get_runtime_transient("dc1") is None


def test_expire_launching_noop_when_connected() -> None:
    registry = RuntimeRegistry()
    registry.register("dc1", FakeConn())
    svc = _service(FakeInjector(), registry=registry, timeout=0)
    svc._live.set_runtime_transient("dc1", RuntimeState.LAUNCHING)
    asyncio.run(svc._expire_launching("dc1"))
    # connected → leave transient untouched (resolver makes connected win anyway)
    assert svc._live.get_runtime_transient("dc1") == RuntimeState.LAUNCHING


def test_stop_kills_and_clears_transient() -> None:
    injector = FakeInjector()
    svc = _service(injector)
    svc._live.set_runtime_transient("dc1", RuntimeState.LAUNCHING)
    asyncio.run(svc.stop("dc1", "/work/repo"))
    assert injector.stopped == ["/work/repo"]
    assert svc._live.get_runtime_transient("dc1") is None


def test_stream_log_delegates_to_injector() -> None:
    svc = _service(FakeInjector())

    async def collect():
        return [chunk async for chunk in svc.stream_log("/work/repo")]

    assert asyncio.run(collect()) == [b"chunk1 ", b"chunk2"]
