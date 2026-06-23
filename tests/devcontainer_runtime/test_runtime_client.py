"""Tests for RuntimeChannelClient — no real Control Plane or network.

The connection factory and backoff are implementation details monkeypatched on the module.
Channel is outbound-only: inbound frames are drained and discarded.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from vibing_protocol import RegisterEnvelope

import vibing_devcontainer_runtime.runtime_client as client_mod
from vibing_devcontainer_runtime.runtime_client import Backoff, RuntimeChannelClient


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

    async def close(self) -> None:
        pass


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


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[object],
    stop_after: int = 1,
    on_registered=None,
) -> tuple[RuntimeChannelClient, FakeConnect, StoppingBackoff]:
    connect = FakeConnect(outcomes)
    monkeypatch.setattr(client_mod, "websockets", SimpleNamespace(connect=connect))
    backoff = StoppingBackoff(stop_after)
    monkeypatch.setattr(client_mod, "Backoff", lambda: backoff)
    client = RuntimeChannelClient("ws://test/ws", RegisterEnvelope(), on_registered=on_registered)
    backoff.client = client
    return client, connect, backoff


# --- backoff --------------------------------------------------------------


def test_backoff_is_bounded_and_resets() -> None:
    backoff = Backoff(initial=1.0, factor=2.0, maximum=4.0)
    assert [backoff.next_delay() for _ in range(6)] == [1.0, 2.0, 4.0, 4.0, 4.0, 4.0]
    backoff.reset()
    assert backoff.next_delay() == 1.0


# --- session behavior -----------------------------------------------------


def test_registers_on_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    ws = FakeWS([])
    client, _, _ = _make_client(monkeypatch, [ws])
    asyncio.run(client.run())

    register = json.loads(ws.sent[0])
    assert register["type"] == "runtime_registered"
    assert register.get("devcontainer_id") is None


def test_inbound_frames_are_drained_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any messages received should be silently discarded, not cause errors."""
    # Script has two message frames then closes; client must drain both without error.
    ws = FakeWS(["frame1", "frame2"])
    client, _, _ = _make_client(monkeypatch, [ws])
    asyncio.run(client.run())
    # recv was called for each frame plus one final call that raised _Closed
    assert len(ws.sent) == 1  # only the register message was sent — frames were discarded


# --- reconnect -----------------------------------------------------------


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
    client = RuntimeChannelClient("ws://x", RegisterEnvelope())
    asyncio.run(client.send_envelope(RegisterEnvelope()))  # no ws -> no raise


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
    client, _, _ = _make_client(monkeypatch, [ws], on_registered=on_registered)
    asyncio.run(client.run())

    assert sequence == ["send", "on_registered"]


def test_send_envelope_sends_to_active_ws(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_envelope forwards to the current WebSocket when connected."""
    done = asyncio.Event()

    async def on_registered() -> None:
        await client.send_envelope(RegisterEnvelope(devcontainer_id="dc-x"))
        done.set()

    ws = FakeWS([done])
    client, _, _ = _make_client(monkeypatch, [ws], on_registered=on_registered)
    asyncio.run(client.run())

    # sent[0] = register, sent[1] = the envelope from on_registered
    assert len(ws.sent) == 2
    payload = json.loads(ws.sent[1])
    assert payload["devcontainer_id"] == "dc-x"
