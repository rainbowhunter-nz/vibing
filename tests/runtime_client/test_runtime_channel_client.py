"""Tests for RuntimeChannelClient — no real Control Plane or network."""

import asyncio
import json
from collections.abc import Awaitable, Callable

from vibing_protocol import (
    Command,
    CommandEnvelope,
    RegisterEnvelope,
    RuntimeEvent,
    TextBlock,
    TranscriptTurn,
)

from vibing_runtime_client.client import (
    Backoff,
    RuntimeChannelClient,
)


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
        assert isinstance(item, str)
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


def _register() -> RegisterEnvelope:
    return RegisterEnvelope(source="host_runtime_worker")


def _client(**kwargs: object) -> RuntimeChannelClient:
    return RuntimeChannelClient("ws://test/ws", _register(), **kwargs)  # type: ignore[arg-type]


def _stop_after(
    client: RuntimeChannelClient, n: int
) -> tuple[Callable[[float], Awaitable[None]], list[float]]:
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) >= n:
            client.stop()

    return sleep, delays


def _command_json(devcontainer_id: str, command_type: str = "start_devcontainer") -> str:
    envelope = CommandEnvelope(command=Command(type=command_type, devcontainer_id=devcontainer_id))
    return json.dumps(envelope.model_dump())


# --- backoff --------------------------------------------------------------


def test_backoff_is_bounded_and_resets() -> None:
    backoff = Backoff(initial=1.0, factor=2.0, maximum=4.0)
    assert [backoff.next_delay() for _ in range(6)] == [1.0, 2.0, 4.0, 4.0, 4.0, 4.0]
    backoff.reset()
    assert backoff.next_delay() == 1.0


# --- session behavior -----------------------------------------------------


def test_registers_then_handles_received_command() -> None:
    entered = asyncio.Event()
    received: list[Command] = []

    async def handler(command: Command, emit: object) -> None:
        received.append(command)
        entered.set()

    ws = FakeWS([_command_json("dc1"), entered])
    client = _client(handler=handler, connect=FakeConnect([ws]))
    sleep, _ = _stop_after(client, 1)
    client._sleep = sleep  # type: ignore[assignment]
    asyncio.run(client.run())

    sent = json.loads(ws.sent[0])
    assert sent["type"] == "runtime_registered"
    assert sent["source"] == "host_runtime_worker"
    assert sent.get("devcontainer_id") is None
    assert [c.devcontainer_id for c in received] == ["dc1"]


def test_consumer_processes_commands_serially_in_fifo_order() -> None:
    order: list[str] = []

    async def handler(command: Command, emit: object) -> None:
        order.append(f"start:{command.devcontainer_id}")
        await asyncio.sleep(0)
        order.append(f"end:{command.devcontainer_id}")

    async def scenario() -> None:
        client = _client(handler=handler)
        queue: asyncio.Queue[Command] = asyncio.Queue()
        queue.put_nowait(Command(type="start_devcontainer", devcontainer_id="a"))
        queue.put_nowait(Command(type="stop_devcontainer", devcontainer_id="b"))
        consumer = asyncio.create_task(client._consume(queue, FakeWS([])))
        await queue.join()
        consumer.cancel()

    asyncio.run(scenario())
    assert order == ["start:a", "end:a", "start:b", "end:b"]


def test_emit_sends_runtime_event_envelope() -> None:
    async def scenario() -> None:
        client = _client()
        ws = FakeWS([])
        emit = client._make_emit(ws)
        await emit(
            RuntimeEvent(
                event_type="devcontainer_started",
                source="host_runtime_worker",
                devcontainer_id="dc1",
            )
        )
        sent = json.loads(ws.sent[0])
        assert sent["type"] == "runtime_event"
        assert sent["event"]["event_type"] == "devcontainer_started"
        assert sent["event"]["devcontainer_id"] == "dc1"

    asyncio.run(scenario())


# --- transcript request/reply (VIB-104) -----------------------------------


def _transcript_request_json(request_id: str, agent_session_id: str) -> str:
    return json.dumps(
        {
            "type": "transcript_request",
            "request_id": request_id,
            "agent_session_id": agent_session_id,
        }
    )


def test_transcript_request_dispatches_handler_and_replies() -> None:
    done = asyncio.Event()
    asked: list[str] = []

    async def transcript_handler(agent_session_id: str) -> list[TranscriptTurn]:
        asked.append(agent_session_id)
        return [TranscriptTurn(role="user", blocks=[TextBlock(text="hi")], at="t")]

    ws = FakeWS([_transcript_request_json("req-9", "sess-7"), done])

    async def watcher() -> None:
        # let the read-loop process the request and send the reply
        while len(ws.sent) < 2:
            await asyncio.sleep(0)
        done.set()

    client = _client(transcript_handler=transcript_handler, connect=FakeConnect([ws]))
    sleep, _ = _stop_after(client, 1)
    client._sleep = sleep  # type: ignore[assignment]

    async def scenario() -> None:
        await asyncio.gather(client.run(), watcher())

    asyncio.run(scenario())

    assert asked == ["sess-7"]
    reply = json.loads(ws.sent[1])  # sent[0] is the register envelope
    assert reply["type"] == "transcript_response"
    assert reply["request_id"] == "req-9"
    assert reply["turns"][0]["blocks"][0] == {"kind": "text", "text": "hi"}


# --- reconnect / no-replay ------------------------------------------------


def test_reconnects_with_bounded_backoff_after_failures() -> None:
    connect = FakeConnect([ConnectionRefusedError(), ConnectionRefusedError(), FakeWS([])])
    client = _client(connect=connect)
    sleep, delays = _stop_after(client, 3)
    client._sleep = sleep  # type: ignore[assignment]
    asyncio.run(client.run())

    assert connect.calls == 3  # two failures + one success
    assert delays == [0.5, 1.0, 0.5]  # exponential growth, then reset after the success


def test_in_flight_command_not_replayed_after_reconnect() -> None:
    entered = asyncio.Event()
    block = asyncio.Event()  # never set: handler stays in-flight
    starts: list[str] = []

    async def handler(command: Command, emit: object) -> None:
        starts.append(command.devcontainer_id or "")
        entered.set()
        await block.wait()

    ws1 = FakeWS([_command_json("dc1"), entered])  # close once the command is picked up
    ws2 = FakeWS([])  # fresh session, nothing queued
    connect = FakeConnect([ws1, ws2])
    client = _client(handler=handler, connect=connect)
    sleep, _ = _stop_after(client, 2)
    client._sleep = sleep  # type: ignore[assignment]
    asyncio.run(client.run())

    assert starts == ["dc1"]  # handled once in session 1, not replayed in session 2
    assert connect.calls == 2
