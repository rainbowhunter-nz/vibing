"""Tests for the per-session turn-delta fan-out (VIB-109/VIB-111, ADR-0010).

subscribe() now returns (replay, queue) where queue receives (event_id, data) tuples.
"""

import queue

from vibing_api.core.session_stream import SessionStreamRegistry


def test_publish_reaches_only_subscribers_of_that_session() -> None:
    reg = SessionStreamRegistry()
    _, a = reg.subscribe("sess-a")
    _, b = reg.subscribe("sess-b")

    reg.publish("sess-a", "delta-1")

    event_id, data = a.get_nowait()
    assert data == "delta-1"
    assert b.empty()


def test_multiple_subscribers_each_receive() -> None:
    reg = SessionStreamRegistry()
    _, a1 = reg.subscribe("s")
    _, a2 = reg.subscribe("s")

    reg.publish("s", "x")

    _, d1 = a1.get_nowait()
    _, d2 = a2.get_nowait()
    assert d1 == "x"
    assert d2 == "x"


def test_unsubscribe_stops_delivery_and_cleans_up() -> None:
    reg = SessionStreamRegistry()
    _, q = reg.subscribe("s")
    assert reg.subscriber_count("s") == 1

    reg.unsubscribe("s", q)
    assert reg.subscriber_count("s") == 0

    reg.publish("s", "x")  # no subscribers — no error
    assert q.empty()


def test_publish_to_unknown_session_is_noop() -> None:
    reg = SessionStreamRegistry()
    reg.publish("ghost", "x")  # no raise


def test_unsubscribe_unknown_queue_is_noop() -> None:
    reg = SessionStreamRegistry()
    reg.subscribe("s")
    reg.unsubscribe("s", queue.SimpleQueue())  # different queue — no raise
