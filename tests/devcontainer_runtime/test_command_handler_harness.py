import asyncio
from typing import Any

from pydantic import BaseModel

from vibing_devcontainer_runtime.claude_runner import ClaudeCodeRunner
from vibing_devcontainer_runtime.command_handler import AgentCommandHandler
from vibing_devcontainer_runtime.harness.base import HarnessStatus
from vibing_protocol import Command, CommandType, RuntimeEventEnvelope


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def authenticate(self, harness: str, blob: dict[str, Any]) -> HarnessStatus:
        self.calls.append((harness, blob))
        return HarnessStatus(name=harness, installed=True, authenticated=True)


async def _collect(handler: AgentCommandHandler, command: Command) -> list[BaseModel]:
    sent: list[BaseModel] = []

    async def send(env: BaseModel) -> None:
        sent.append(env)

    await handler.handle(command, send)
    return sent


def test_authenticate_harness_emits_harness_status():
    manager = FakeManager()
    handler = AgentCommandHandler(ClaudeCodeRunner(), harness_manager=manager)  # type: ignore[arg-type]
    cmd = Command(
        type=CommandType.AUTHENTICATE_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex", "credentials": {"auth_json": {"OPENAI_API_KEY": "sk"}}},
    )
    sent = asyncio.run(_collect(handler, cmd))
    assert manager.calls == [("codex", {"auth_json": {"OPENAI_API_KEY": "sk"}})]
    envelopes = [e for e in sent if isinstance(e, RuntimeEventEnvelope)]
    assert len(envelopes) == 1
    evt = envelopes[0].event
    assert evt.event_type == "harness_status"
    assert evt.payload == {"harness": "codex", "installed": True, "authenticated": True}
    assert evt.devcontainer_id == "dc-1"
