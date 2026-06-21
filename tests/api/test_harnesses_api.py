from vibing_protocol import HarnessStatusItem

from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_intake import record_harness_status


def test_list_harnesses_unknown_when_no_cache(client, devcontainer_id) -> None:
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "known": False}


def test_list_harnesses_known_after_runtime_push(client, devcontainer_id) -> None:
    live: LiveStateStore = client.app.state.live_state
    record_harness_status(
        live,
        devcontainer_id,
        [HarnessStatusItem(name="codex", installed=True, authenticated=False)],
        None,
    )
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    body = resp.json()
    assert body["known"] is True
    assert body["items"] == [{"name": "codex", "installed": True, "authenticated": False}]


def test_record_harness_status_evict(client, devcontainer_id) -> None:
    live: LiveStateStore = client.app.state.live_state
    record_harness_status(
        live,
        devcontainer_id,
        [HarnessStatusItem(name="codex", installed=True, authenticated=True)],
        None,
    )
    live.evict_harness(devcontainer_id)
    resp = client.get(f"/api/v1/devcontainers/{devcontainer_id}/harnesses")
    assert resp.json()["known"] is False
