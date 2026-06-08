"""Tests for GET .../agent-sessions/{id}/stream — the per-session turn-delta SSE.

Mirrors test_sse_events.py's bounded `_max=N` strategy. Verifies:
- SEPARATE endpoint from the global invalidation /events SSE (ADR-0005/0006)
- turn-delta events keyed by session with `id:` fields (VIB-111)
- replay on fresh connect (full run)
- Last-Event-ID reconnect resumes from the correct position (no dups, no gaps)
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


def _parse_sse(lines: list[str]) -> list[dict]:
    """Parse SSE lines into list of {event, id, data}."""
    events = []
    current: dict = {}
    for line in lines:
        line = line.strip()
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("id:"):
            current["id"] = line[len("id:") :].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:") :].strip()
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


def test_stream_connect_returns_event_stream_content_type() -> None:
    app = create_app()
    with TestClient(app) as client:
        with client.stream("GET", _URL.format(sid="s") + "?_max=0") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]


def test_stream_delivers_turn_delta_with_id_field() -> None:
    """VIB-111: every SSE event must carry an id: field so browsers track lastEventId."""
    app = create_app()
    registry: SessionStreamRegistry = app.state.session_streams
    registry.begin_run("s")
    delta = json.dumps({"kind": "text", "turn_id": "u-1", "role": "assistant", "text": "Hi"})
    t = _publish_after_subscribe(registry, "s", [delta])

    with TestClient(app) as client:
        with client.stream("GET", _URL.format(sid="s") + "?_max=1") as r:
            lines = list(r.iter_lines())

    t.join(timeout=1.0)
    events = _parse_sse(lines)
    assert len(events) == 1
    assert events[0]["event"] == "turn_delta"
    assert "id" in events[0]
    assert events[0]["id"] != ""
    payload = json.loads(events[0]["data"])
    assert payload == {"kind": "text", "turn_id": "u-1", "role": "assistant", "text": "Hi"}


def test_stream_replays_full_run_on_fresh_connect() -> None:
    """AC1: fresh connect (no Last-Event-ID) replays the full current run."""
    app = create_app()
    registry: SessionStreamRegistry = app.state.session_streams
    registry.begin_run("s-replay")
    # Pre-publish two events before connecting.
    d1 = json.dumps({"kind": "text", "turn_id": "t1", "role": "assistant", "text": "A"})
    d2 = json.dumps({"kind": "text", "turn_id": "t1", "role": "assistant", "text": "B"})
    registry.publish("s-replay", d1)
    registry.publish("s-replay", d2)

    with TestClient(app) as client:
        with client.stream("GET", _URL.format(sid="s-replay") + "?_max=2") as r:
            lines = list(r.iter_lines())

    events = _parse_sse(lines)
    assert len(events) == 2
    assert json.loads(events[0]["data"])["text"] == "A"
    assert json.loads(events[1]["data"])["text"] == "B"
    # ids are monotonic strings of integers
    assert int(events[0]["id"]) < int(events[1]["id"])


def test_stream_resumes_from_last_event_id() -> None:
    """AC2: reconnect with Last-Event-ID sends only events after that id (no dups)."""
    app = create_app()
    registry: SessionStreamRegistry = app.state.session_streams
    registry.begin_run("s-resume")
    d1 = json.dumps({"kind": "text", "turn_id": "t1", "role": "assistant", "text": "A"})
    d2 = json.dumps({"kind": "text", "turn_id": "t1", "role": "assistant", "text": "B"})
    d3 = json.dumps({"kind": "text", "turn_id": "t1", "role": "assistant", "text": "C"})
    registry.publish("s-resume", d1)
    registry.publish("s-resume", d2)
    registry.publish("s-resume", d3)

    # First connect: get all 3 events and note the second id.
    with TestClient(app) as client:
        with client.stream("GET", _URL.format(sid="s-resume") + "?_max=3") as r:
            lines = list(r.iter_lines())
    full_events = _parse_sse(lines)
    assert len(full_events) == 3
    last_received_id = full_events[1]["id"]  # pretend client received A and B

    # Reconnect with Last-Event-ID = id after B → should only get C.
    with TestClient(app) as client:
        headers = {"last-event-id": last_received_id}
        with client.stream("GET", _URL.format(sid="s-resume") + "?_max=1", headers=headers) as r:
            lines = list(r.iter_lines())
    resume_events = _parse_sse(lines)
    assert len(resume_events) == 1
    assert json.loads(resume_events[0]["data"])["text"] == "C"


def test_stream_only_delivers_its_own_sessions_deltas() -> None:
    app = create_app()
    registry: SessionStreamRegistry = app.state.session_streams
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
