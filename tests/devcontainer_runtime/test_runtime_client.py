"""Tests for RuntimeChannelClient — no real Control Plane or network.

The connection factory and backoff are implementation details monkeypatched on the module.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from vibing_protocol import (
    Command,
    CommandEnvelope,
    HarnessStatusEnvelope,
    HarnessStatusItem,
    RegisterEnvelope,
)
from vibing_protocol.commands import CommandType

import vibing_devcontainer_runtime.runtime_client as client_mod
from vibing_devcontainer_runtime.runtime_client import Backoff, RuntimeChannelClient, SendFn


class _Closed(Exception):
    """Stand-in for a dropped connection."""


class FakeWS:
    """Scriptable websocket. recv() walks `script`: str -> return; Event -> await then close."""

    def __init__(self, script: list[object]) -> None:
        self._script = list(script)
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        if not self._script:
            raise _Closed
        item = self._script.pop(0)
        if isinstance(item, asyncio.Event):
            await item.wait()
            raise _Closed
        assert isinstance(item, str), f"Script items must be str or Event, got {type(item)}"
        return item


class FakeConnect:
    """Async-CM factory. Each outcome is a FakeWS (success) or an Exception (connect fails)."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, url: str) -> "FakeConnect._CM":
        self.calls += 1
        return self._CM(self._outcomes.pop(0))

    class _CM:
        def __init__(self, outcome: object) -> None:
            self._outcome = outcome

        async def __aenter__(self) -> object:
            if isinstance(self._outcome, BaseException):
                raise self._outcome
            return self._outcome

        async def __aexit__(self, *_exc: object) -> bool:
            return False


class StoppingBackoff(Backoff):
    """Records real delays but sleeps 0; stops the client after `stop_after` delays."""

    def __init__(self, stop_after: int) -> None:
        super().__init__()
        self.delays: list[float] = []
        self.client: RuntimeChannelClient | None = None
        self._stop_after = stop_after

    def next_delay(self) -> float:
        self.delays.append(super().next_delay())
        if len(self.delays) >= self._stop_after and self.client is not None:
            self.client.stop()
        return 0.0


async def _ignore_command(command: Command, send: SendFn) -> None:
    return None


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[object],
    handler: object = _ignore_command,
    stop_after: int = 1,
) -> tuple[RuntimeChannelClient, FakeConnect, StoppingBackoff]:
    connect = FakeConnect(outcomes)
    monkeypatch.setattr(client_mod, "websockets", SimpleNamespace(connect=connect))
    backoff = StoppingBackoff(stop_after)
    monkeypatch.setattr(client_mod, "Backoff", lambda: backoff)
    client = RuntimeChannelClient(
        "ws://test/ws",
        RegisterEnvelope(),
        handler,  # type: ignore[arg-type]
    )
    backoff.client = client
    return client, connect, backoff


def _command_json(devcontainer_id: str) -> str:
    envelope = CommandEnvelope(
        command=Command(type=CommandType.AUTHENTICATE_HARNESS, devcontainer_id=devcontainer_id)
    )
    return json.dumps(envelope.model_dump())


# --- backoff --------------------------------------------------------------


def test_backoff_is_bounded_and_resets() -> None:
    backoff = Backoff(initial=1.0, factor=2.0, maximum=4.0)
    assert [backoff.next_delay() for _ in range(6)] == [1.0, 2.0, 4.0, 4.0, 4.0, 4.0]
    backoff.reset()
    assert backoff.next_delay() == 1.0


# --- session behavior -----------------------------------------------------


def test_registers_then_handler_gets_command_and_sends_on_same_ws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    received: list[Command] = []

    async def handler(command: Command, send: SendFn) -> None:
        received.append(command)
        await send(
            HarnessStatusEnvelope(
                devcontainer_id=command.devcontainer_id or "",
                items=[HarnessStatusItem(name="codex", installed=True, authenticated=True)],
            )
        )
        entered.set()

    ws = FakeWS([_command_json("dc1"), entered])
    client, _, _ = _make_client(monkeypatch, [ws], handler=handler)
    asyncio.run(client.run())

    register = json.loads(ws.sent[0])
    assert register["type"] == "runtime_registered"
    assert register.get("devcontainer_id") is None
    assert [c.devcontainer_id for c in received] == ["dc1"]
    sent_envelope = json.loads(ws.sent[1])
    assert sent_envelope["type"] == "harness_status"
    assert sent_envelope["devcontainer_id"] == "dc1"


def test_commands_run_serially_in_fifo_order(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = asyncio.Event()
    order: list[str] = []

    async def handler(command: Command, send: SendFn) -> None:
        order.append(f"start:{command.devcontainer_id}")
        await asyncio.sleep(0)  # yield so a concurrent handler could interleave
        order.append(f"end:{command.devcontainer_id}")
        if command.devcontainer_id == "b":
            entered.set()

    ws = FakeWS([_command_json("a"), _command_json("b"), entered])
    client, _, _ = _make_client(monkeypatch, [ws], handler=handler)
    asyncio.run(client.run())

    assert order == ["start:a", "end:a", "start:b", "end:b"]


def test_unknown_message_types_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = asyncio.Event()
    handled: list[str] = []

    async def handler(command: Command, send: SendFn) -> None:
        handled.append(command.devcontainer_id or "")
        entered.set()

    ws = FakeWS(["not json", json.dumps({"type": "mystery"}), _command_json("dc1"), entered])
    client, _, _ = _make_client(monkeypatch, [ws], handler=handler)
    asyncio.run(client.run())

    assert handled == ["dc1"]


# --- reconnect / no-replay ------------------------------------------------


def test_reconnects_with_bounded_backoff_after_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [ConnectionRefusedError(), ConnectionRefusedError(), FakeWS([])]
    client, connect, backoff = _make_client(monkeypatch, outcomes, stop_after=3)
    asyncio.run(client.run())

    assert connect.calls == 3  # two failures + one success
    assert backoff.delays == [0.5, 1.0, 0.5]  # exponential growth, then reset after the success


def test_stop_closes_active_websocket_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = asyncio.Event()
    unblock = asyncio.Event()

    class ClosingWS(FakeWS):
        async def close(self) -> None:
            closed.set()
            unblock.set()

    ws = ClosingWS([unblock])
    client, _, _ = _make_client(monkeypatch, [ws], stop_after=99)

    async def scenario() -> None:
        run_task = asyncio.create_task(client.run())
        await asyncio.sleep(0)
        client.stop()
        await asyncio.wait_for(run_task, timeout=1.0)

    asyncio.run(scenario())
    assert closed.is_set()


def test_send_envelope_warns_and_noops_when_disconnected() -> None:
    async def handler(cmd: Command, send: SendFn) -> None:
        return None

    client = RuntimeChannelClient("ws://x", RegisterEnvelope(), handler)
    asyncio.run(client.send_envelope(RegisterEnvelope()))  # no ws -> no raise


def test_in_flight_command_not_replayed_after_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = asyncio.Event()
    block = asyncio.Event()  # never set: handler stays in-flight
    starts: list[str] = []

    async def handler(command: Command, send: SendFn) -> None:
        starts.append(command.devcontainer_id or "")
        entered.set()
        await block.wait()

    ws1 = FakeWS([_command_json("dc1"), entered])  # close once command is picked up
    ws2 = FakeWS([])  # fresh session, nothing queued
    client, connect, _ = _make_client(monkeypatch, [ws1, ws2], handler=handler, stop_after=2)
    asyncio.run(client.run())

    assert starts == ["dc1"]  # handled once in session 1, not replayed in session 2
    assert connect.calls == 2


# --- on_registered hook ---------------------------------------------------


def test_on_registered_fires_after_registration_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """on_registered is called right after the registration message is sent."""
    sequence: list[str] = []
    hooked = asyncio.Event()

    class SequencingWS(FakeWS):
        async def send(self, data: str) -> None:
            sequence.append("send")
            await super().send(data)

    async def on_registered() -> None:
        sequence.append("on_registered")
        hooked.set()

    ws = SequencingWS([hooked])
    connect = FakeConnect([ws])
    monkeypatch.setattr(client_mod, "websockets", SimpleNamespace(connect=connect))
    backoff = StoppingBackoff(1)
    monkeypatch.setattr(client_mod, "Backoff", lambda: backoff)
    client = RuntimeChannelClient(
        "ws://test/ws",
        RegisterEnvelope(),
        _ignore_command,
        on_registered=on_registered,
    )
    backoff.client = client
    asyncio.run(client.run())

    assert sequence == ["send", "on_registered"]
