import asyncio

from vibing_api.core import harness_service
from vibing_api.core.live_state import LiveStateStore
from tests.harness.fakes import FakeExecutor
from vibing_harness import CommandResult


def test_compute_status_runs_all_descriptors():
    ex = FakeExecutor(
        {
            "codex": CommandResult(0, "", ""),
            "cursor-agent": CommandResult(127, "", ""),
        }
    )
    statuses = asyncio.run(harness_service.compute_status(ex))
    by = {s.name: s for s in statuses}
    assert by["codex"].installed is True
    assert by["cursor"].installed is False


def test_refresh_caches_and_returns():
    ex = FakeExecutor({"codex": CommandResult(0, "", ""), "cursor-agent": CommandResult(0, "", "")})
    live = LiveStateStore()
    statuses = asyncio.run(harness_service.refresh(live, "dc1", ex))
    assert live.get_harness("dc1") == statuses


def test_authenticate_writes_credentials():
    ex = FakeExecutor({"codex": CommandResult(0, "", "")})

    async def go():
        return [
            line
            async for line in harness_service.authenticate_stream(
                ex, "codex", {"auth_json": {"K": "v"}}
            )
        ]

    asyncio.run(go())
    assert ".codex/auth.json" in ex.files
