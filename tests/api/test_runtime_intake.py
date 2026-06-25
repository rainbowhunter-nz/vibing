from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_intake import record_delegated_runs
from vibing_protocol import DelegatedRunItem


def test_record_writes_cache_and_publishes() -> None:
    store = LiveStateStore()
    published: list[SseEvent] = []

    class _B(Broadcaster):
        def publish(self, event: SseEvent) -> None:  # type: ignore[override]
            published.append(event)

    item = DelegatedRunItem(
        run_id="r1",
        harness="codex",
        model="m",
        title="seed task",
        status="running",
        started_at="2026-06-20T00:00:00+00:00",
    )
    record_delegated_runs(store, "dc1", [item], _B())
    assert [r.run_id for r in store.get_delegated_runs("dc1")] == ["r1"]
    assert published == [SseEvent(scope="delegated_runs", ids=["dc1"])]
