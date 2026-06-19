"""Tests for RuntimeChannelClient — no real Control Plane or network.

The connection factory and backoff are implementation details, not constructor
parameters: tests monkeypatch them on the client module.
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from pydantic import BaseModel
from vibing_protocol import (
    Command,
    CommandEnvelope,
    RegisterEnvelope,
    RuntimeEvent,
    RuntimeEventEnvelope,
    RuntimeEventSource,
    EventType,
)

from vibing_protocol.commands import CommandType
import vibing_runtime_client.client as client_mod
from vibing_runtime_client.client import Backoff, RuntimeChannelClient, SendFn


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
        elif isinstance(item, str):
            return item
        else:
            assert False, f"Script items must be str or Event, got {type(item)}"


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
    handler: Any = _ignore_command,
    stop_after: int = 1,
) -> tuple[RuntimeChannelClient, FakeConnect, StoppingBackoff]:
    connect = FakeConnect(outcomes)
    monkeypatch.setattr(client_mod, "websockets", SimpleNamespace(connect=connect))
    backoff = StoppingBackoff(stop_after)
    monkeypatch.setattr(client_mod, "Backoff", lambda: backoff)
    client = RuntimeChannelClient(
        "ws://test/ws", RegisterEnvelope(source=RuntimeEventSource.HOST_RUNTIME_WORKER), handler
    )
    backoff.client = client
    return client, connect, backoff


def _command_json(
    devcontainer_id: str, command_type: CommandType = CommandType.START_DEVCONTAINER
) -> str:
    envelope = CommandEnvelope(command=Command(type=command_type, devcontainer_id=devcontainer_id))
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
            RuntimeEventEnvelope(
                event=RuntimeEvent(
                    event_type=EventType.DEVCONTAINER_STARTING,
                    source=RuntimeEventSource.DEVCONTAINER_RUNTIME_AGENT,
                    devcontainer_id=command.devcontainer_id,
                )
            )
        )
        entered.set()

    ws = FakeWS([_command_json("dc1"), entered])
    client, _, _ = _make_client(monkeypatch, [ws], handler=handler)
    asyncio.run(client.run())

    register = json.loads(ws.sent[0])
    assert register["type"] == "runtime_registered"
    assert register["source"] == "host_runtime_worker"
    assert register.get("devcontainer_id") is None
    assert [c.devcontainer_id for c in received] == ["dc1"]
    event = json.loads(ws.sent[1])  # handler's send reaches the same ws, serialized
    assert event["type"] == "runtime_event"
    assert event["event"]["devcontainer_id"] == "dc1"


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


# --- request/reply (ADR-0009): generic correlation, no domain types --------


class _EchoReply(BaseModel):
    type: Literal["echo_response"] = "echo_response"
    request_id: str
    payload: str


def _request_json(request_id: str) -> str:
    return json.dumps({"type": "echo_request", "request_id": request_id, "payload": "hi"})


def test_registered_request_handler_replies_on_same_ws(monkeypatch: pytest.MonkeyPatch) -> None:
    async def respond(message: dict[str, Any]) -> _EchoReply:
        return _EchoReply(request_id=message["request_id"], payload=message["payload"])

    # The reply is awaited inline in the read loop, so it is sent before the next recv.
    ws = FakeWS([_request_json("req-9")])
    client, _, _ = _make_client(monkeypatch, [ws])
    client.on_request("echo_request", respond)
    asyncio.run(client.run())

    reply = json.loads(ws.sent[1])  # sent[0] is the register envelope
    assert reply == {"type": "echo_response", "request_id": "req-9", "payload": "hi"}


def test_failing_request_handler_sends_no_reply_and_session_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    handled: list[str] = []

    async def respond(message: dict[str, Any]) -> _EchoReply:
        raise RuntimeError("boom")

    async def handler(command: Command, send: SendFn) -> None:
        handled.append(command.devcontainer_id or "")
        entered.set()

    ws = FakeWS([_request_json("req-1"), _command_json("dc1"), entered])
    client, _, _ = _make_client(monkeypatch, [ws], handler=handler)
    client.on_request("echo_request", respond)
    asyncio.run(client.run())

    assert handled == ["dc1"]  # the command after the failing request is still processed
    assert len(ws.sent) == 1  # register envelope only, no reply


def test_unregistered_message_types_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
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

    ws1 = FakeWS([_command_json("dc1"), entered])  # close once the command is picked up
    ws2 = FakeWS([])  # fresh session, nothing queued
    client, connect, _ = _make_client(monkeypatch, [ws1, ws2], handler=handler, stop_after=2)
    asyncio.run(client.run())

    assert starts == ["dc1"]  # handled once in session 1, not replayed in session 2
    assert connect.calls == 2
