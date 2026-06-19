"""Tests for the runtime agent WebSocket channel (/runtime/agent/ws).

Uses a minimal FastAPI app fixture — does NOT depend on create_app() / _APP_IMPORTABLE.
"""

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
from vibing_api.repositories.harness_status import HarnessStatusRepository


class _FakeBroadcaster:
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
def spy() -> _FakeBroadcaster:
    return _FakeBroadcaster()


@pytest.fixture()
def ws_client(db_path: Path, spy: _FakeBroadcaster) -> Iterator[TestClient]:
    from vibing_api.api.routes import runtime

    app = FastAPI()
    app.state.runtime_manager = RuntimeRegistry()
    app.state.broadcaster = spy
    app.include_router(runtime.router, prefix="/api/v1")

    with TestClient(app) as client:
        yield client


def _seed_devcontainer(name: str = "dc") -> str:
    with get_connection() as conn:
        dc = DevcontainerRepository(conn).create(name=name, local_path="/tmp/dc")
        conn.commit()
    return dc.id


AGENT_WS_URL = "/api/v1/runtime/agent/ws"


def _register_msg(dc_id: str) -> dict[str, Any]:
    return {"type": "runtime_registered", "devcontainer_id": dc_id}


def _harness_status_msg(dc_id: str) -> dict[str, Any]:
    return {
        "type": "harness_status",
        "devcontainer_id": dc_id,
        "items": [
            {"name": "claude", "installed": True, "authenticated": True},
            {"name": "gh", "installed": False, "authenticated": False},
        ],
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_agent_registers(ws_client: TestClient, db_path: Path) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_register_msg(dc_id))
        assert ws.receive_json() == {"type": "registered"}


def test_agent_missing_id_is_rejected(ws_client: TestClient) -> None:
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json({"type": "runtime_registered"})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4400


def test_duplicate_agent_is_rejected(ws_client: TestClient, db_path: Path) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws1:
        ws1.send_json(_register_msg(dc_id))
        assert ws1.receive_json() == {"type": "registered"}
        with ws_client.websocket_connect(AGENT_WS_URL) as ws2:
            ws2.send_json(_register_msg(dc_id))
            with pytest.raises(WebSocketDisconnect) as exc:
                ws2.receive_json()
            assert exc.value.code == 4409


def test_agent_slot_freed_after_disconnect(ws_client: TestClient, db_path: Path) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws1:
        ws1.send_json(_register_msg(dc_id))
        assert ws1.receive_json() == {"type": "registered"}
    with ws_client.websocket_connect(AGENT_WS_URL) as ws2:
        ws2.send_json(_register_msg(dc_id))
        assert ws2.receive_json() == {"type": "registered"}


# ---------------------------------------------------------------------------
# harness_status intake
# ---------------------------------------------------------------------------


def test_harness_status_persisted(ws_client: TestClient, db_path: Path) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_register_msg(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        ws.send_json(_harness_status_msg(dc_id))

    with get_connection() as conn:
        rows = HarnessStatusRepository(conn).list(dc_id)
    assert len(rows) == 2
    by_name = {r.name: r for r in rows}
    assert by_name["claude"].installed is True
    assert by_name["claude"].authenticated is True
    assert by_name["gh"].installed is False


def test_harness_status_publishes_harnesses_invalidation(
    ws_client: TestClient, spy: _FakeBroadcaster, db_path: Path
) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_register_msg(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        spy.published.clear()  # clear the connect broadcast
        ws.send_json(_harness_status_msg(dc_id))

    harness_events = [e for e in spy.published if e.scope == "harnesses"]
    assert len(harness_events) == 1
    assert harness_events[0].ids == [dc_id]


def test_harness_status_ignored_before_registration(ws_client: TestClient, db_path: Path) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_harness_status_msg(dc_id))
        # Should be ignored (no crash)

    with get_connection() as conn:
        rows = HarnessStatusRepository(conn).list(dc_id)
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# RuntimeRegistry unit tests
# ---------------------------------------------------------------------------


def test_registry_register_and_check() -> None:
    from unittest.mock import MagicMock

    reg = RuntimeRegistry()
    ws = MagicMock()
    assert reg.register("dc-1", ws) is True
    assert reg.is_connected("dc-1")


def test_registry_reject_duplicate() -> None:
    from unittest.mock import MagicMock

    reg = RuntimeRegistry()
    ws1, ws2 = MagicMock(), MagicMock()
    assert reg.register("dc-1", ws1) is True
    assert reg.register("dc-1", ws2) is False


def test_registry_unregister() -> None:
    from unittest.mock import MagicMock

    reg = RuntimeRegistry()
    ws = MagicMock()
    reg.register("dc-1", ws)
    reg.unregister("dc-1", ws)
    assert not reg.is_connected("dc-1")
