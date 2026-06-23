import asyncio

from vibing_harness import CommandResult, Executor, HarnessDescriptor, HarnessStatus
from .fakes import FakeExecutor


class _Stub(HarnessDescriptor):
    name = "stub"

    def __init__(self, installed: bool, authed: bool) -> None:
        self._installed = installed
        self._authed = authed

    async def is_installed(self, ex: Executor) -> bool:
        return self._installed

    def install_argv(self) -> list[str]:
        return []

    async def install(self, ex: Executor) -> None: ...

    async def is_authenticated(self, ex: Executor) -> bool:
        return self._authed

    async def write_credentials(self, ex: Executor, blob: dict) -> None: ...

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return []

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout


def test_status_skips_auth_check_when_not_installed():
    s = asyncio.run(_Stub(installed=False, authed=True).status(FakeExecutor()))
    assert s == HarnessStatus(name="stub", installed=False, authenticated=False)


def test_status_reports_auth_when_installed():
    s = asyncio.run(_Stub(installed=True, authed=True).status(FakeExecutor()))
    assert s == HarnessStatus(name="stub", installed=True, authenticated=True)


def test_command_result_is_frozen():
    r = CommandResult(0, "out", "err")
    assert (r.returncode, r.stdout, r.stderr) == (0, "out", "err")
