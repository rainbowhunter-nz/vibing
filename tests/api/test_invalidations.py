"""Tests for SSE invalidation broadcast."""

from vibing_api.core.broadcaster import Broadcaster, SseEvent

_DC = "dc-1"


def test_broadcaster_publishes_devcontainer_scope() -> None:
    b = Broadcaster()
    q = b.subscribe()
    b.publish(SseEvent(scope="devcontainers", ids=[_DC]))
    event = q.get_nowait()
    assert event.scope == "devcontainers"
    assert event.ids == [_DC]


def test_broadcaster_publishes_harnesses_scope() -> None:
    b = Broadcaster()
    q = b.subscribe()
    b.publish(SseEvent(scope="harnesses", ids=[_DC]))
    event = q.get_nowait()
    assert event.scope == "harnesses"


def test_broadcaster_publishes_delegated_runs_scope() -> None:
    b = Broadcaster()
    q = b.subscribe()
    b.publish(SseEvent(scope="delegated_runs", ids=[_DC]))
    event = q.get_nowait()
    assert event.scope == "delegated_runs"
    assert event.ids == [_DC]
