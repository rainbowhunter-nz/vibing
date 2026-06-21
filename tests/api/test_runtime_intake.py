"""Unit tests for persist functions in runtime_intake."""

from vibing_api.core.broadcaster import SseEvent
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_intake import record_harness_status
from vibing_protocol import HarnessStatusItem


class _FakeBroadcaster:
    def __init__(self) -> None:
        self.published: list[SseEvent] = []

    def publish(self, event: SseEvent) -> None:
        self.published.append(event)


def test_record_harness_status_sets_live_state() -> None:
    live = LiveStateStore()
    items = [
        HarnessStatusItem(name="claude", installed=True, authenticated=False),
        HarnessStatusItem(name="gh", installed=False, authenticated=False),
    ]
    record_harness_status(live, "dc1", items)
    stored = live.get_harness("dc1")
    assert stored is not None
    by_name = {i.name: i for i in stored}
    assert by_name["claude"].installed is True
    assert by_name["claude"].authenticated is False
    assert by_name["gh"].installed is False


def test_record_harness_status_overwrites_previous() -> None:
    live = LiveStateStore()
    record_harness_status(
        live, "dc1", [HarnessStatusItem(name="claude", installed=False, authenticated=False)]
    )
    record_harness_status(
        live, "dc1", [HarnessStatusItem(name="claude", installed=True, authenticated=True)]
    )
    stored = live.get_harness("dc1")
    assert stored is not None
    assert stored[0].installed is True
    assert stored[0].authenticated is True


def test_record_harness_status_publishes_sse_event() -> None:
    live = LiveStateStore()
    broadcaster = _FakeBroadcaster()
    record_harness_status(
        live,
        "dc1",
        [HarnessStatusItem(name="gh", installed=True, authenticated=True)],
        broadcaster,  # type: ignore[arg-type]
    )
    assert len(broadcaster.published) == 1
    evt = broadcaster.published[0]
    assert evt.scope == "harnesses"
    assert evt.ids == ["dc1"]


def test_record_harness_status_no_broadcaster_is_ok() -> None:
    live = LiveStateStore()
    record_harness_status(
        live, "dc1", [HarnessStatusItem(name="gh", installed=True, authenticated=False)]
    )
    assert live.get_harness("dc1") is not None
