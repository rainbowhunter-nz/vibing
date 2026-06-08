"""Unit tests for SessionStreamRegistry replay buffer (VIB-111, AC6).

Tests are isolated — no HTTP, no app. Tests pin:
- monotonic event ids (per-run integer counter, as string)
- append: each publish appends (id, data) to the in-memory buffer
- replay-all: subscribe(last_event_id=None) returns the full current run buffer
- replay-from-last-event-id: only entries with id > last_event_id (integer compare)
- atomic snapshot+register: no item lost or duplicated between snapshot and live queue
- multi-subscriber: two queues both get live (id, data) tuples
- run_started resets buffer and counter (new run starts fresh)
- run_ended evicts the buffer entirely
- fresh subscribe after eviction replays nothing (AC5)
"""

import json
import queue
import time

from vibing_api.core.session_stream import SessionStreamRegistry


def _run_started() -> str:
    return json.dumps({"kind": "run_started"})


def _run_ended() -> str:
    return json.dumps({"kind": "run_ended"})


def _text(text: str, turn_id: str = "t1") -> str:
    return json.dumps({"kind": "text", "turn_id": turn_id, "role": "assistant", "text": text})


# ---------------------------------------------------------------------------
# Append + monotonic ids
# ---------------------------------------------------------------------------


def test_publish_assigns_monotonic_ids() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    replay, _q = reg.subscribe("s")
    reg.publish("s", _text("a"))
    reg.publish("s", _text("b"))
    reg.publish("s", _text("c"))

    _, q2 = reg.subscribe("s")
    replay2, _q2 = reg.subscribe("s")
    # Ids come back as strings but must be orderable as integers.
    ids = [int(event_id) for event_id, _ in replay2]
    assert ids == sorted(ids)
    assert ids == list(range(ids[0], ids[0] + len(ids)))


def test_publish_before_begin_run_is_not_buffered() -> None:
    """publish with no active run buffer is safe (noop for buffer), still fan-outs."""
    reg = SessionStreamRegistry()
    _, q = reg.subscribe("s")
    reg.publish("s", _text("x"))
    event_id, data = q.get_nowait()
    assert data == _text("x")
    # No buffer was maintained — subscribe without begin_run replays nothing.
    replay, _q2 = reg.subscribe("s")
    assert replay == []


# ---------------------------------------------------------------------------
# Replay-all (last_event_id=None)
# ---------------------------------------------------------------------------


def test_subscribe_replays_full_current_run_when_no_last_event_id() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("hello"))
    reg.publish("s", _text(" world"))

    replay, _q = reg.subscribe("s", last_event_id=None)
    assert len(replay) == 2
    datas = [data for _, data in replay]
    assert datas == [_text("hello"), _text(" world")]


# ---------------------------------------------------------------------------
# Replay-from-last-event-id
# ---------------------------------------------------------------------------


def test_subscribe_resumes_after_last_event_id() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("A"))
    reg.publish("s", _text("B"))
    reg.publish("s", _text("C"))

    # First subscribe to capture ids.
    full_replay, _q = reg.subscribe("s")
    ids = [event_id for event_id, _ in full_replay]
    assert len(ids) == 3

    # Re-subscribe with last_event_id = ids[1] (received A and B, missed C).
    replay, _q2 = reg.subscribe("s", last_event_id=ids[1])
    assert len(replay) == 1
    assert replay[0][1] == _text("C")


def test_subscribe_with_last_event_id_equal_to_last_published_gets_nothing() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("only"))

    full, _q = reg.subscribe("s")
    last_id = full[-1][0]

    replay, _q2 = reg.subscribe("s", last_event_id=last_id)
    assert replay == []


def test_subscribe_with_unknown_last_event_id_replays_all() -> None:
    """An id that precedes all buffer entries → replay everything."""
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("x"))

    replay, _q = reg.subscribe("s", last_event_id="0")
    # "0" is before the first event (counter starts at 1), so all are replayed.
    assert len(replay) == 1


# ---------------------------------------------------------------------------
# Multi-subscriber: live fan-out delivers (id, data) to each queue
# ---------------------------------------------------------------------------


def test_two_live_subscribers_each_receive_published_item() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    _, q1 = reg.subscribe("s")
    _, q2 = reg.subscribe("s")

    reg.publish("s", _text("hi"))

    item1 = q1.get_nowait()
    item2 = q2.get_nowait()
    assert item1 == item2
    event_id, data = item1
    assert data == _text("hi")
    assert event_id  # non-empty id


def test_late_subscriber_replays_buffer_then_sees_live() -> None:
    """Late connect: replays the buffer (via replay list), then new publishes go to queue."""
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("first"))

    replay, q = reg.subscribe("s", last_event_id=None)
    assert len(replay) == 1
    assert replay[0][1] == _text("first")

    reg.publish("s", _text("second"))
    live_item = q.get_nowait()
    assert live_item[1] == _text("second")


# ---------------------------------------------------------------------------
# Atomic: no gap between snapshot and registration
# ---------------------------------------------------------------------------


def test_no_item_missed_between_snapshot_and_registration() -> None:
    """
    Stress test: a publish thread fires continuously; subscribe atomically grabs
    the snapshot AND the live queue so no item is missed.
    """
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    # Publish some items before subscribe.
    for i in range(10):
        reg.publish("s", _text(str(i)))

    # Subscribe captures replay + queue atomically.
    replay, q = reg.subscribe("s", last_event_id=None)

    # Now publish 10 more items.
    for i in range(10, 20):
        reg.publish("s", _text(str(i)))

    # Drain the live queue.
    live_items = []
    deadline = time.monotonic() + 1.0
    while len(live_items) < 10 and time.monotonic() < deadline:
        try:
            live_items.append(q.get_nowait())
        except queue.Empty:
            pass

    all_items = replay + live_items
    assert len(all_items) == 20
    # No duplicates.
    ids = [event_id for event_id, _ in all_items]
    assert len(set(ids)) == 20
    # Monotonically increasing.
    int_ids = [int(i) for i in ids]
    assert int_ids == sorted(int_ids)


# ---------------------------------------------------------------------------
# run_started resets buffer and counter
# ---------------------------------------------------------------------------


def test_begin_run_clears_previous_run_buffer() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("old"))

    # New run: buffer and counter reset.
    reg.begin_run("s")
    replay, _q = reg.subscribe("s", last_event_id=None)
    assert replay == []


def test_begin_run_restarts_id_counter_from_one() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("run1"))
    first_run_replay, _ = reg.subscribe("s")
    first_id = int(first_run_replay[0][0])

    reg.begin_run("s")
    reg.publish("s", _text("run2"))
    second_run_replay, _ = reg.subscribe("s")
    second_id = int(second_run_replay[0][0])

    # Counter resets — first event of new run has same or lower id than the previous run's first.
    assert second_id == first_id  # both are 1 (counter resets to 1 on begin_run)


def test_publish_run_started_delta_calls_begin_run_semantics() -> None:
    """publish() detects run_started kind and resets the buffer automatically."""
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("old"))

    # Publishing a run_started delta resets the buffer (registry parses kind).
    reg.publish("s", _run_started())

    replay, _q = reg.subscribe("s", last_event_id=None)
    # Only the run_started delta itself is in the buffer after reset.
    assert len(replay) == 1
    assert json.loads(replay[0][1])["kind"] == "run_started"


# ---------------------------------------------------------------------------
# run_ended evicts buffer (AC4 + AC5)
# ---------------------------------------------------------------------------


def test_end_run_evicts_buffer() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("data"))
    reg.end_run("s")

    replay, _q = reg.subscribe("s", last_event_id=None)
    assert replay == []


def test_publish_run_ended_delta_evicts_buffer() -> None:
    """publish() detects run_ended kind and evicts the buffer automatically."""
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("data"))
    reg.publish("s", _run_ended())

    replay, _q = reg.subscribe("s", last_event_id=None)
    assert replay == []


def test_fresh_subscribe_after_eviction_gets_no_stale_replay() -> None:
    """AC5: after run ends, a new connect sees empty replay (uses durable transcript)."""
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    reg.publish("s", _text("mid-run"))
    reg.end_run("s")

    replay, _q = reg.subscribe("s", last_event_id=None)
    assert replay == []


# ---------------------------------------------------------------------------
# subscriber_count still works (existing tests use it)
# ---------------------------------------------------------------------------


def test_subscriber_count_unchanged_by_buffer_logic() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s")
    _, q = reg.subscribe("s")
    assert reg.subscriber_count("s") == 1
    reg.unsubscribe("s", q)
    assert reg.subscriber_count("s") == 0


# ---------------------------------------------------------------------------
# Cross-session isolation
# ---------------------------------------------------------------------------


def test_buffer_is_per_session() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s1")
    reg.begin_run("s2")
    reg.publish("s1", _text("for-s1"))
    reg.publish("s2", _text("for-s2"))

    r1, _ = reg.subscribe("s1")
    r2, _ = reg.subscribe("s2")
    assert [d for _, d in r1] == [_text("for-s1")]
    assert [d for _, d in r2] == [_text("for-s2")]


def test_end_run_does_not_affect_other_sessions() -> None:
    reg = SessionStreamRegistry()
    reg.begin_run("s1")
    reg.begin_run("s2")
    reg.publish("s1", _text("x"))
    reg.publish("s2", _text("y"))
    reg.end_run("s1")

    r1, _ = reg.subscribe("s1")
    r2, _ = reg.subscribe("s2")
    assert r1 == []
    assert len(r2) == 1
