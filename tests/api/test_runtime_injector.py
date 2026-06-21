import asyncio

from vibing_api.core.devcontainer_cli import RunResult
from vibing_api.core.runtime_injector import RuntimeInjector


def test_inject_by_path_resolves_container_then_injects() -> None:
    calls = []

    async def runner(command):
        calls.append(command)
        if command[:3] == ["docker", "ps", "-q"]:
            return RunResult(0, "deadbeef\n", "")
        return RunResult(0, "", "")

    injector = RuntimeInjector(runner=runner, wheel_dir="/nonexistent")
    # wheel_dir missing → inject() returns early after resolving; we assert resolve happened
    asyncio.run(injector.inject_by_path("dc1", "/work/repo"))
    assert any(
        c[:3] == ["docker", "ps", "-q"] and "label=devcontainer.local_folder=/work/repo" in c
        for c in calls
    )
