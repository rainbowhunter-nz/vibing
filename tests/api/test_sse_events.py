"""Tests for GET /api/v1/events SSE endpoint and the broadcaster primitive.

SSE testing strategy: the TestClient (httpx ASGI transport) buffers the entire
response before returning from stream(), so we test infinite SSE streams via a
bounded `_max=N` query param that makes the generator finite after N events.

For event delivery tests, a background thread publishes events once the generator
has subscribed (detected via broadcaster.subscriber_count > 0). The generator then
reads the event immediately and terminates (_max=1 or _max=N).
"""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.main import create_app


def _publish_after_subscribe(
    broadcaster: Broadcaster, events: list[SseEvent], delay: float = 0.02
) -> threading.Thread:
    """Return a daemon thread that publishes events once a subscriber exists."""

    def _run() -> None:
        deadline = time.monotonic() + 2.0
        while broadcaster.subscriber_count == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        for event in events:
            broadcaster.publish(event)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# --- broadcaster unit tests ---


def test_broadcaster_subscribe_and_publish() -> None:
    b = Broadcaster()
    q = b.subscribe()
    b.publish(SseEvent(scope="devcontainers", ids=["dc-1"]))
    assert not q.empty()
    event = q.get_nowait()
    assert event.scope == "devcontainers"
    assert event.ids == ["dc-1"]


def test_broadcaster_multiple_subscribers() -> None:
    b = Broadcaster()
    q1 = b.subscribe()
    q2 = b.subscribe()
    b.publish(SseEvent(scope="inbox", ids=["e-1"]))
    assert q1.get_nowait().scope == "inbox"
    assert q2.get_nowait().scope == "inbox"


def test_broadcaster_unsubscribe_removes_queue() -> None:
    b = Broadcaster()
    q = b.subscribe()
    assert b.subscriber_count == 1
    b.unsubscribe(q)
    assert b.subscriber_count == 0


def test_broadcaster_unsubscribe_stops_delivery() -> None:
    b = Broadcaster()
    q = b.subscribe()
    b.unsubscribe(q)
    b.publish(SseEvent(scope="approvals", ids=[]))
    assert q.empty()


def test_sse_event_all_scopes_valid() -> None:
    """All required scopes can be constructed without error."""
    for scope in ("devcontainers", "agent_sessions", "inbox", "approvals", "runtime"):
        e = SseEvent(scope=scope, ids=["x"])
        assert e.scope == scope


# --- SSE endpoint tests ---


def test_sse_connect_returns_200_with_event_stream_content_type() -> None:
    """AC1: GET /api/v1/events opens an SSE stream."""
    app = create_app()
    # _max=0: generator exits immediately (no events) so TestClient doesn't hang
    with TestClient(app) as client:
        with client.stream("GET", "/api/v1/events?_max=0") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]


def test_sse_delivers_event_with_correct_shape() -> None:
    """AC2: Events have stable shape: event_type, scope, ids."""
    app = create_app()
    t = _publish_after_subscribe(
        app.state.broadcaster, [SseEvent(scope="devcontainers", ids=["dc-1"])]
    )

    with TestClient(app) as client:
        # _max=1: generator stops after reading one event
        with client.stream("GET", "/api/v1/events?_max=1") as r:
            assert r.status_code == 200
            data_lines = [
                line.strip()[len("data:") :].strip()
                for line in r.iter_lines()
                if line.strip().startswith("data:")
            ]

    t.join(timeout=1.0)

    assert len(data_lines) == 1
    payload = json.loads(data_lines[0])
    assert payload["scope"] == "devcontainers"
    assert payload["ids"] == ["dc-1"]
    assert payload["event_type"] == "invalidate"
    assert set(payload.keys()) == {"event_type", "scope", "ids"}


def test_sse_delivers_all_required_scopes() -> None:
    """AC3: All five scopes are deliverable through the broadcaster."""
    scopes: list[str] = ["devcontainers", "agent_sessions", "inbox", "approvals", "runtime"]
    app = create_app()
    events = [SseEvent(scope=scope, ids=["x"]) for scope in scopes]  # type: ignore[arg-type]
    t = _publish_after_subscribe(app.state.broadcaster, events)

    with TestClient(app) as client:
        with client.stream("GET", f"/api/v1/events?_max={len(scopes)}") as r:
            data_lines = [
                line.strip()[len("data:") :].strip()
                for line in r.iter_lines()
                if line.strip().startswith("data:")
            ]

    t.join(timeout=1.0)

    received_scopes = [json.loads(d)["scope"] for d in data_lines]
    assert received_scopes == scopes


def test_sse_heartbeat_keepalive_mechanism() -> None:
    """AC4: FastAPI's EventSourceResponse uses a patchable _PING_INTERVAL for keepalive.

    We verify the hook exists and has a sensible default; patching it is the
    documented way to speed up keepalive for testing.
    """
    import fastapi.sse as sse_module
    from fastapi.sse import KEEPALIVE_COMMENT

    assert hasattr(sse_module, "_PING_INTERVAL")
    assert sse_module._PING_INTERVAL > 0
    # Wire format for keepalive comment
    assert KEEPALIVE_COMMENT == b": ping\n\n"


def test_sse_heartbeat_appears_in_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC4: Patching _PING_INTERVAL to a short value causes keepalive pings in the stream."""
    import fastapi.routing as routing_module

    # Must patch in fastapi.routing (where _PING_INTERVAL is used), not fastapi.sse
    ping_interval = 0.05
    monkeypatch.setattr(routing_module, "_PING_INTERVAL", ping_interval)

    app = create_app()

    # Delay publishing long enough for the keepalive timer to fire at least once
    def _delayed_publish() -> None:
        deadline = time.monotonic() + 2.0
        while app.state.broadcaster.subscriber_count == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        # wait at least 2x the ping interval so a ping is injected before the event
        time.sleep(ping_interval * 2)
        app.state.broadcaster.publish(SseEvent(scope="inbox", ids=[]))

    t = threading.Thread(target=_delayed_publish, daemon=True)
    t.start()

    with TestClient(app) as client:
        with client.stream("GET", "/api/v1/events?_max=1") as r:
            raw_lines = [line.strip() for line in r.iter_lines() if line.strip()]

    t.join(timeout=2.0)

    # With a very short ping interval the keepalive comment should appear
    comment_lines = [line for line in raw_lines if line.startswith(":")]
    assert comment_lines, f"expected at least one keepalive comment, got: {raw_lines}"


def test_sse_disconnect_cleans_up_subscriber() -> None:
    """AC5: Subscriber count returns to 0 after the SSE generator finishes."""
    app = create_app()
    broadcaster = app.state.broadcaster

    assert broadcaster.subscriber_count == 0

    t = _publish_after_subscribe(broadcaster, [SseEvent(scope="runtime", ids=[])])

    with TestClient(app) as client:
        with client.stream("GET", "/api/v1/events?_max=1") as r:
            r.read()  # consume the full finite response

    t.join(timeout=1.0)

    # generator's finally block ran unsubscribe
    assert broadcaster.subscriber_count == 0


def test_sse_is_separate_from_runtime_websocket() -> None:
    """AC7: SSE endpoint is independent from the WS runtime channel."""
    app = create_app()
    with TestClient(app) as client:
        with client.stream("GET", "/api/v1/events?_max=0") as r:
            assert r.status_code == 200

        with client.websocket_connect("/api/v1/runtime/ws") as ws:
            ws.send_json({"type": "runtime_registered", "source": "host_runtime_worker"})
            ack = ws.receive_json()
            assert ack == {"type": "registered"}
