"""Tests for SSE invalidation broadcast.

Updated for ADR-0014/0015: event-sourcing layer removed; broadcaster is tested directly.
"""

from fastapi.testclient import TestClient

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.runtime_intake import persist_harness_status


_DC = "dc-1"
_SESSION = "sess-1"


# ---------------------------------------------------------------------------
# Broadcaster unit tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# persist_harness_status broadcasts after commit
# ---------------------------------------------------------------------------


def test_persist_harness_status_broadcasts(client: TestClient) -> None:
    """persist_harness_status publishes a harnesses invalidation after commit."""
    from vibing_protocol import HarnessStatusItem

    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"})
    assert resp.status_code == 201
    dc_id = resp.json()["id"]

    class _Spy:
        def __init__(self) -> None:
            self.published: list[SseEvent] = []

        def publish(self, event: SseEvent) -> None:
            self.published.append(event)

    spy = _Spy()
    persist_harness_status(
        dc_id,
        [HarnessStatusItem(name="codex", installed=True, authenticated=False)],
        spy,  # type: ignore[arg-type]
    )

    assert len(spy.published) == 1
    assert spy.published[0].scope == "harnesses"
    assert dc_id in spy.published[0].ids
