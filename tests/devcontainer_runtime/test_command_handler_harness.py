import asyncio
from typing import Any

from pydantic import BaseModel

from vibing_devcontainer_runtime.command_handler import HarnessCommandHandler
from vibing_devcontainer_runtime.harness.base import HarnessStatus
from vibing_protocol import Command, CommandType, HarnessStatusEnvelope


class FakeHarnessManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.install_called: bool = False
        self.statuses: dict[str, HarnessStatus] = {
            "codex": HarnessStatus(name="codex", installed=False, authenticated=False),
            "cursor": HarnessStatus(name="cursor", installed=False, authenticated=False),
        }

    async def authenticate(self, harness: str, credentials: dict[str, Any]) -> HarnessStatus:
        self.calls.append((harness, credentials))
        self.statuses[harness] = HarnessStatus(name=harness, installed=True, authenticated=True)
        return self.statuses[harness]

    async def install(self, harness: str) -> HarnessStatus:
        self.install_called = True
        self.statuses[harness] = HarnessStatus(name=harness, installed=True, authenticated=False)
        return self.statuses[harness]

    async def list_statuses(self) -> list[HarnessStatus]:
        return list(self.statuses.values())


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
    # Reports the FULL list so other harnesses aren't dropped from the cache.
    reported = {i.name: (i.installed, i.authenticated) for i in env.items}
    assert reported == {"codex": (True, True), "cursor": (False, False)}


def test_install_command_installs_and_reports_full_list():
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
    # Other harnesses survive: install reports the whole list, not just the one.
    reported = {i.name: i.installed for i in env.items}
    assert reported == {"codex": True, "cursor": False}


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
    manager.statuses = {
        "codex": HarnessStatus(name="codex", installed=True, authenticated=False),
        "cursor": HarnessStatus(name="cursor", installed=False, authenticated=False),
    }
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
