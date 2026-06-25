import vibing_harness
from vibing_protocol import DelegatedRunItem

from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.vocabularies import DevcontainerStatus


def test_transient_set_get_clear() -> None:
    store = LiveStateStore()
    assert store.get_transient("dc1") is None
    store.set_transient("dc1", DevcontainerStatus.STARTING)
    assert store.get_transient("dc1") == DevcontainerStatus.STARTING
    store.clear_transient("dc1")
    assert store.get_transient("dc1") is None


def test_clear_transient_is_idempotent() -> None:
    store = LiveStateStore()
    store.clear_transient("missing")  # no raise


def test_harness_cache_set_get_evict() -> None:
    store = LiveStateStore()
    assert store.get_harness("dc1") is None
    items = [vibing_harness.HarnessStatus(name="codex", installed=True, authenticated=False)]
    store.set_harness("dc1", items)
    assert store.get_harness("dc1") == items
    store.evict_harness("dc1")
    assert store.get_harness("dc1") is None


def test_runtime_transient_set_get_clear() -> None:
    from vibing_api.core.live_state import LiveStateStore
    from vibing_api.core.vocabularies import RuntimeState

    store = LiveStateStore()
    assert store.get_runtime_transient("dc1") is None
    store.set_runtime_transient("dc1", RuntimeState.LAUNCHING)
    assert store.get_runtime_transient("dc1") == RuntimeState.LAUNCHING
    store.clear_runtime_transient("dc1")
    assert store.get_runtime_transient("dc1") is None


def _item(run_id: str) -> DelegatedRunItem:
    return DelegatedRunItem(
        run_id=run_id,
        harness="codex",
        model="m",
        title="seed task",
        status="running",
        started_at="2026-06-20T00:00:00+00:00",
    )


def test_delegated_runs_set_get_evict() -> None:
    store = LiveStateStore()
    assert store.get_delegated_runs("dc1") is None
    store.set_delegated_runs("dc1", [_item("run-1")])
    assert [r.run_id for r in store.get_delegated_runs("dc1")] == ["run-1"]
    store.set_delegated_runs("dc1", [_item("run-2")])  # replace, not append
    assert [r.run_id for r in store.get_delegated_runs("dc1")] == ["run-2"]
    store.evict_delegated_runs("dc1")
    assert store.get_delegated_runs("dc1") is None
