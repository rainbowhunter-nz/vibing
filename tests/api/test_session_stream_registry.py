"""Tests for the per-session turn-delta fan-out (VIB-109, ADR-0010)."""

import queue

from vibing_api.core.session_stream import SessionStreamRegistry


def test_publish_reaches_only_subscribers_of_that_session() -> None:
    reg = SessionStreamRegistry()
    a = reg.subscribe("sess-a")
    b = reg.subscribe("sess-b")

    reg.publish("sess-a", "delta-1")

    assert a.get_nowait() == "delta-1"
    assert b.empty()


def test_multiple_subscribers_each_receive() -> None:
    reg = SessionStreamRegistry()
    a1 = reg.subscribe("s")
    a2 = reg.subscribe("s")

    reg.publish("s", "x")

    assert a1.get_nowait() == "x"
    assert a2.get_nowait() == "x"


def test_unsubscribe_stops_delivery_and_cleans_up() -> None:
    reg = SessionStreamRegistry()
    q = reg.subscribe("s")
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
