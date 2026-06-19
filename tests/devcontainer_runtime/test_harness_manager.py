import asyncio
from typing import Any

import pytest

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness_manager import HarnessManager


class FakeAdapter(HarnessAdapter):
    def __init__(self, name: str, installed: bool, authed: bool) -> None:
        self.name = name
        self._installed = installed
        self._authed = authed
        self.installed_called = False
        self.written: dict[str, Any] | None = None

    async def is_installed(self) -> bool:
        return self._installed

    async def install(self) -> None:
        self.installed_called = True
        self._installed = True

    async def is_authenticated(self) -> bool:
        return self._authed

    def write_credentials(self, blob: dict[str, Any]) -> None:
        self.written = blob
        self._authed = True

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return []

    def spawn_env(self) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout


def test_list_statuses_reports_each_adapter():
    mgr = HarnessManager(
        {"codex": FakeAdapter("codex", True, False), "cursor": FakeAdapter("cursor", False, False)}
    )
    statuses = {s.name: s for s in asyncio.run(mgr.list_statuses())}
    assert statuses["codex"].installed is True and statuses["codex"].authenticated is False
    assert statuses["cursor"].installed is False


def test_authenticate_installs_when_missing_then_writes_creds():
    adapter = FakeAdapter("codex", installed=False, authed=False)
    mgr = HarnessManager({"codex": adapter})
    status = asyncio.run(mgr.authenticate("codex", {"auth_json": {"k": "v"}}))
    assert adapter.installed_called is True
    assert adapter.written == {"auth_json": {"k": "v"}}
    assert status.installed is True and status.authenticated is True


def test_authenticate_unknown_harness_raises():
    mgr = HarnessManager({"codex": FakeAdapter("codex", True, True)})
    with pytest.raises(KeyError):
        asyncio.run(mgr.authenticate("nope", {}))
