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
from vibing_api.core.live_state import LiveStateStore
from vibing_api.core.runtime_channel import RuntimeRegistry
from vibing_api.repositories.delegated_runs import DelegatedRunRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository


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
    app.state.live_state = LiveStateStore()
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


def _delegated_runs_msg(dc_id: str) -> dict[str, Any]:
    return {
        "type": "delegated_runs",
        "devcontainer_id": dc_id,
        "items": [
            {
                "run_id": "run-1",
                "harness": "codex",
                "model": "m",
                "status": "running",
                "result": None,
                "error": None,
                "started_at": "2026-06-20T00:00:00+00:00",
            }
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


# ---------------------------------------------------------------------------
# delegated_runs intake
# ---------------------------------------------------------------------------


def test_delegated_runs_snapshot_is_persisted(ws_client: TestClient, db_path: Path) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_register_msg(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        ws.send_json(_delegated_runs_msg(dc_id))

    with get_connection() as conn:
        rows = DelegatedRunRepository(conn).list(dc_id)
    assert [r.run_id for r in rows] == ["run-1"]


def test_delegated_runs_publishes_sse_invalidation(
    ws_client: TestClient, spy: _FakeBroadcaster, db_path: Path
) -> None:
    dc_id = _seed_devcontainer()
    with ws_client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_register_msg(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        spy.published.clear()
        ws.send_json(_delegated_runs_msg(dc_id))

    dr_events = [e for e in spy.published if e.scope == "delegated_runs"]
    assert len(dr_events) == 1
    assert dr_events[0].ids == [dc_id]
