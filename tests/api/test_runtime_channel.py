"""Unit tests for runtime_channel: the WebSocket connection adapter and persistence."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from vibing_api.core.broadcaster import SseEvent
from vibing_api.core.database import get_connection, init_db
from vibing_api.core.runtime_channel import WebSocketRuntimeConnection, persist_harness_status
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.harness_status import HarnessStatusRepository
from vibing_protocol import Command, CommandEnvelope, CommandType, HarnessStatusItem


class _FakeBroadcaster:
    def __init__(self) -> None:
        self.published: list[SseEvent] = []

    def publish(self, event: SseEvent) -> None:
        self.published.append(event)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vibing_api.core.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    init_db()


def test_websocket_runtime_connection_sends_command_envelope() -> None:
    websocket = AsyncMock()
    connection = WebSocketRuntimeConnection(websocket)
    command = Command(
        type=CommandType.INSTALL_HARNESS,
        devcontainer_id="dc-1",
        payload={"harness": "codex"},
    )

    asyncio.run(connection.send(command))

    websocket.send_json.assert_awaited_once()
    sent = websocket.send_json.call_args[0][0]
    assert sent == CommandEnvelope(command=command).model_dump()
    assert sent["type"] == "command"
    assert sent["command"]["payload"] == {"harness": "codex"}


def _seed_devcontainer() -> str:
    with get_connection() as conn:
        dc = DevcontainerRepository(conn).create(name="test", local_path="/tmp/test")
        conn.commit()
    return dc.id


def test_persist_harness_status_upserts_rows() -> None:
    dc_id = _seed_devcontainer()
    items = [
        HarnessStatusItem(name="claude", installed=True, authenticated=False),
        HarnessStatusItem(name="gh", installed=False, authenticated=False),
    ]
    persist_harness_status(dc_id, items)

    with get_connection() as conn:
        rows = HarnessStatusRepository(conn).list(dc_id)
    assert len(rows) == 2
    by_name = {r.name: r for r in rows}
    assert by_name["claude"].installed is True
    assert by_name["claude"].authenticated is False
    assert by_name["gh"].installed is False


def test_persist_harness_status_upserts_on_second_call() -> None:
    dc_id = _seed_devcontainer()
    persist_harness_status(
        dc_id, [HarnessStatusItem(name="claude", installed=False, authenticated=False)]
    )
    persist_harness_status(
        dc_id, [HarnessStatusItem(name="claude", installed=True, authenticated=True)]
    )

    with get_connection() as conn:
        rows = HarnessStatusRepository(conn).list(dc_id)
    assert len(rows) == 1
    assert rows[0].installed is True
    assert rows[0].authenticated is True


def test_persist_harness_status_publishes_harnesses_sse_event() -> None:
    dc_id = _seed_devcontainer()
    broadcaster = _FakeBroadcaster()
    persist_harness_status(
        dc_id, [HarnessStatusItem(name="gh", installed=True, authenticated=True)], broadcaster
    )

    assert len(broadcaster.published) == 1
    evt = broadcaster.published[0]
    assert evt.scope == "harnesses"
    assert evt.ids == [dc_id]


def test_persist_harness_status_no_broadcaster_is_ok() -> None:
    dc_id = _seed_devcontainer()
    # Must not raise when broadcaster is None
    persist_harness_status(
        dc_id, [HarnessStatusItem(name="gh", installed=True, authenticated=False)]
    )
