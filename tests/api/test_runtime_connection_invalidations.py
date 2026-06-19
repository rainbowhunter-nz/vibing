"""Tests for SSE invalidation broadcasts on runtime agent connect/disconnect."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from vibing_api.core.broadcaster import SseEvent
from vibing_api.core.database import get_connection, init_db
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.repositories.devcontainers import DevcontainerRepository

AGENT_WS_URL = "/api/v1/runtime/agent/ws"
_DC_ID = "placeholder"  # real id seeded per-test


class CapturingBroadcaster:
    def __init__(self) -> None:
        self.published: list[SseEvent] = []

    def publish(self, event: SseEvent) -> None:
        self.published.append(event)


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from vibing_api.core.config import settings

    path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{path}")
    init_db()
    return path


@pytest.fixture()
def spy() -> CapturingBroadcaster:
    return CapturingBroadcaster()


@pytest.fixture()
def ws_client(db_path: Path, spy: CapturingBroadcaster) -> Iterator[TestClient]:
    from vibing_api.api.routes import runtime

    app = FastAPI()
    app.state.runtime_manager = RuntimeRegistry()
    app.state.broadcaster = spy
    app.include_router(runtime.router, prefix="/api/v1")

    with TestClient(app) as client:
        yield client


def _seed_devcontainer() -> str:
    with get_connection() as conn:
        dc = DevcontainerRepository(conn).create(name="dc", local_path="/tmp/dc")
        conn.commit()
    return dc.id


def _register_msg(dc_id: str) -> dict[str, Any]:
    return {"type": "runtime_registered", "devcontainer_id": dc_id}


# ---------------------------------------------------------------------------
# AC: Agent connect + disconnect broadcasts `runtime` scope keyed by devcontainer_id
# ---------------------------------------------------------------------------


def test_agent_connect_broadcasts_runtime_invalidation(
    ws_client: TestClient, spy: CapturingBroadcaster, db_path: Path
) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_register_msg(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        assert len(spy.published) == 1
        evt = spy.published[0]
        assert evt.scope == "runtime"
        assert evt.ids == [dc_id]

    # disconnect
    assert len(spy.published) == 2
    assert spy.published[1].scope == "runtime"
    assert spy.published[1].ids == [dc_id]


def test_agent_disconnect_broadcasts_runtime_invalidation(
    ws_client: TestClient, spy: CapturingBroadcaster, db_path: Path
) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_register_msg(dc_id))
        ws.receive_json()
        before_disconnect = len(spy.published)

    assert len(spy.published) == before_disconnect + 1
    assert spy.published[-1].scope == "runtime"
    assert spy.published[-1].ids == [dc_id]


# ---------------------------------------------------------------------------
# Rejected / invalid connections must NOT broadcast
# ---------------------------------------------------------------------------


def test_invalid_envelope_does_not_broadcast(
    ws_client: TestClient, spy: CapturingBroadcaster
) -> None:
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json({"type": "runtime_registered"})  # missing devcontainer_id -> rejected
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    assert spy.published == []


def test_rejected_duplicate_does_not_extra_broadcast(
    ws_client: TestClient, spy: CapturingBroadcaster, db_path: Path
) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws1:
        ws1.send_json(_register_msg(dc_id))
        ws1.receive_json()
        connect_count = len(spy.published)  # 1 from first connect

        with ws_client.websocket_connect(AGENT_WS_URL) as ws2:
            ws2.send_json(_register_msg(dc_id))
            with pytest.raises(WebSocketDisconnect):
                ws2.receive_json()
        # rejected ws2 must not add events
        assert len(spy.published) == connect_count
