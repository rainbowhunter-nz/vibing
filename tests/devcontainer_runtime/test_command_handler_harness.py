import asyncio
from typing import Any

from pydantic import BaseModel

from vibing_devcontainer_runtime.command_handler import HarnessCommandHandler
from vibing_devcontainer_runtime.harness.base import HarnessStatus
from vibing_protocol import Command, CommandType, HarnessStatusEnvelope


class FakeHarnessManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._statuses: list[HarnessStatus] = []
        self.install_called: bool = False

    async def authenticate(self, harness: str, credentials: dict[str, Any]) -> HarnessStatus:
        self.calls.append((harness, credentials))
        return HarnessStatus(name=harness, installed=True, authenticated=True)

    async def install(self, harness: str) -> HarnessStatus:
        self.install_called = True
        return HarnessStatus(name=harness, installed=True, authenticated=True)

    async def list_statuses(self) -> list[HarnessStatus]:
        return self._statuses


async def _send_all(handler: HarnessCommandHandler, command: Command) -> list[BaseModel]:
    sent: list[BaseModel] = []

    async def send(env: BaseModel) -> None:
        sent.append(env)

    await handler.handle(command, send)
    return sent


def _make_handler(manager: FakeHarnessManager) -> HarnessCommandHandler:
    return HarnessCommandHandler(manager, devcontainer_id="dc-1")


def test_authenticate_harness_calls_manager_and_sends_envelope():
    manager = FakeHarnessManager()
    handler = _make_handler(manager)
    cmd = Command(
        type=CommandType.AUTHENTICATE_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex", "credentials": {"auth_json": {"OPENAI_API_KEY": "sk"}}},
    )
    sent = asyncio.run(_send_all(handler, cmd))
    assert manager.calls == [("codex", {"auth_json": {"OPENAI_API_KEY": "sk"}})]
    assert len(sent) == 1
    env = sent[0]
    assert isinstance(env, HarnessStatusEnvelope)
    assert env.devcontainer_id == "dc-1"
    assert len(env.items) == 1
    item = env.items[0]
    assert item.name == "codex"
    assert item.installed is True
    assert item.authenticated is True


def test_install_command_installs_and_reports():
    manager = FakeHarnessManager()
    handler = _make_handler(manager)
    cmd = Command(
        type=CommandType.INSTALL_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex"},
    )
    sent = asyncio.run(_send_all(handler, cmd))
    assert manager.install_called
    assert len(sent) == 1
    env = sent[0]
    assert isinstance(env, HarnessStatusEnvelope)
    assert env.items[0].name == "codex"
    assert env.items[0].installed is True


def test_non_authenticate_command_is_ignored():
    manager = FakeHarnessManager()
    handler = _make_handler(manager)
    # Bypass validation to simulate an unknown/unsupported command type on the wire.
    cmd = Command.model_construct(type="unknown_command", devcontainer_id="dc-1")
    sent = asyncio.run(_send_all(handler, cmd))
    assert sent == []
    assert manager.calls == []


def test_report_all_sends_full_list():
    manager = FakeHarnessManager()
    manager._statuses = [
        HarnessStatus(name="codex", installed=True, authenticated=False),
        HarnessStatus(name="cursor", installed=False, authenticated=False),
    ]
    handler = _make_handler(manager)
    sent: list[BaseModel] = []

    async def _run() -> None:
        async def send(env: BaseModel) -> None:
            sent.append(env)

        await handler.report_all(send)

    asyncio.run(_run())
    assert len(sent) == 1
    env = sent[0]
    assert isinstance(env, HarnessStatusEnvelope)
    assert env.devcontainer_id == "dc-1"
    assert [(i.name, i.installed, i.authenticated) for i in env.items] == [
        ("codex", True, False),
        ("cursor", False, False),
    ]
