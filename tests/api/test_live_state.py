from vibing_protocol import HarnessStatusItem

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
    items = [HarnessStatusItem(name="codex", installed=True, authenticated=False)]
    store.set_harness("dc1", items)
    assert store.get_harness("dc1") == items
    store.evict_harness("dc1")
    assert store.get_harness("dc1") is None
