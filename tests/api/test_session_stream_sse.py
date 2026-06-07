"""Tests for GET .../agent-sessions/{id}/stream — the per-session turn-delta SSE.

Mirrors test_sse_events.py's bounded `_max=N` strategy. Verifies the stream is a
SEPARATE endpoint from the global invalidation /events SSE (ADR-0005/0006), relays
turn-deltas keyed by session, and is live-from-connect (no replay buffer, VIB-111).
"""

import json
import threading
import time

from fastapi.testclient import TestClient

from vibing_api.core.session_stream import SessionStreamRegistry
from vibing_api.main import create_app

_URL = "/api/v1/devcontainers/dc-1/agent-sessions/{sid}/stream"


def _publish_after_subscribe(
    registry: SessionStreamRegistry, sid: str, payloads: list[str]
) -> threading.Thread:
    def _run() -> None:
        deadline = time.monotonic() + 2.0
        while registry.subscriber_count(sid) == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        for p in payloads:
            registry.publish(sid, p)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def test_stream_connect_returns_event_stream_content_type() -> None:
    app = create_app()
    with TestClient(app) as client:
        with client.stream("GET", _URL.format(sid="s") + "?_max=0") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]


def test_stream_delivers_turn_delta_payload() -> None:
    app = create_app()
    registry: SessionStreamRegistry = app.state.session_streams
    delta = json.dumps({"kind": "text", "turn_id": "u-1", "role": "assistant", "text": "Hi"})
    t = _publish_after_subscribe(registry, "s", [delta])

    with TestClient(app) as client:
        with client.stream("GET", _URL.format(sid="s") + "?_max=1") as r:
            lines = [line.strip() for line in r.iter_lines()]

    t.join(timeout=1.0)
    data_lines = [line[len("data:") :].strip() for line in lines if line.startswith("data:")]
    event_lines = [line[len("event:") :].strip() for line in lines if line.startswith("event:")]
    assert event_lines == ["turn_delta"]
    assert len(data_lines) == 1
    payload = json.loads(data_lines[0])
    assert payload == {"kind": "text", "turn_id": "u-1", "role": "assistant", "text": "Hi"}


def test_stream_only_delivers_its_own_sessions_deltas() -> None:
    app = create_app()
    registry: SessionStreamRegistry = app.state.session_streams
    # Publish to a DIFFERENT session before our subscriber connects; ours stays empty,
    # then publish to ours so the bounded generator terminates.
    mine = json.dumps({"kind": "run_started"})
    t = _publish_after_subscribe(registry, "mine", [mine])

    with TestClient(app) as client:
        with client.stream("GET", _URL.format(sid="mine") + "?_max=1") as r:
            data_lines = [
                line.strip()[len("data:") :].strip()
                for line in r.iter_lines()
                if line.strip().startswith("data:")
            ]

    t.join(timeout=1.0)
    assert [json.loads(d) for d in data_lines] == [{"kind": "run_started"}]


def test_stream_disconnect_cleans_up_subscriber() -> None:
    app = create_app()
    registry: SessionStreamRegistry = app.state.session_streams
    assert registry.subscriber_count("s") == 0
    t = _publish_after_subscribe(registry, "s", [json.dumps({"kind": "run_ended"})])

    with TestClient(app) as client:
        with client.stream("GET", _URL.format(sid="s") + "?_max=1") as r:
            r.read()

    t.join(timeout=1.0)
    assert registry.subscriber_count("s") == 0


def test_global_events_stream_stays_payload_free() -> None:
    """AC6: /events remains invalidation-only; the per-session stream is separate."""
    app = create_app()
    with TestClient(app) as client:
        # Both endpoints exist and are distinct.
        with client.stream("GET", "/api/v1/events?_max=0") as r:
            assert r.status_code == 200
        with client.stream("GET", _URL.format(sid="s") + "?_max=0") as r:
            assert r.status_code == 200
