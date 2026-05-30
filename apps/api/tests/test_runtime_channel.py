from collections.abc import Callable
from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.runtime_events import RuntimeEventRepository

WS_URL = "/api/v1/runtime/ws"
_REGISTER = {"type": "runtime_registered", "source": "host_runtime_worker"}


def _create_devcontainer(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _event_envelope(dc_id: str, event_type: str = "devcontainer_started") -> dict[str, Any]:
    return {
        "type": "runtime_event",
        "event": {
            "event_type": event_type,
            "source": "host_runtime_worker",
            "devcontainer_id": dc_id,
        },
    }


def test_worker_registers(client: TestClient) -> None:
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(_REGISTER)
        assert ws.receive_json() == {"type": "registered"}


def test_runtime_event_persisted_and_projected(client: TestClient) -> None:
    dc_id = _create_devcontainer(client)
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        ws.send_json(_event_envelope(dc_id))
    with get_connection() as conn:
        events = RuntimeEventRepository(conn).list_by_devcontainer(dc_id)
        assert len(events) == 1
        assert events[0].event_type == "devcontainer_started"
        assert events[0].source == "host_runtime_worker"
        assert DevcontainerRepository(conn).get(dc_id).status == "running"


def test_second_worker_is_closed(client: TestClient) -> None:
    with client.websocket_connect(WS_URL) as ws1:
        ws1.send_json(_REGISTER)
        assert ws1.receive_json() == {"type": "registered"}
        with client.websocket_connect(WS_URL) as ws2:
            ws2.send_json(_REGISTER)
            with pytest.raises(WebSocketDisconnect) as exc:
                ws2.receive_json()
            assert exc.value.code == 4409


def test_malformed_registration_does_not_claim_slot(client: TestClient) -> None:
    with client.websocket_connect(WS_URL) as ws1:
        ws1.send_json({"type": "runtime_registered", "source": "garbage"})  # invalid source
        with client.websocket_connect(WS_URL) as ws2:  # slot must still be free
            ws2.send_json(_REGISTER)
            assert ws2.receive_json() == {"type": "registered"}


def test_worker_slot_freed_after_disconnect(client: TestClient) -> None:
    with client.websocket_connect(WS_URL) as ws1:
        ws1.send_json(_REGISTER)
        assert ws1.receive_json() == {"type": "registered"}
    with client.websocket_connect(WS_URL) as ws2:
        ws2.send_json(_REGISTER)
        assert ws2.receive_json() == {"type": "registered"}


@pytest.mark.parametrize(
    "send_malformed",
    [
        lambda ws: ws.send_text("not valid json"),
        lambda ws: ws.send_json({"event": {}}),  # missing type
        lambda ws: ws.send_json({"type": "bogus"}),  # unsupported type
        lambda ws: ws.send_json(  # invalid event_type in envelope
            {
                "type": "runtime_event",
                "event": {"event_type": "nope", "source": "host_runtime_worker"},
            }
        ),
    ],
)
def test_malformed_messages_create_no_events(
    client: TestClient, send_malformed: Callable[[Any], None]
) -> None:
    dc_id = _create_devcontainer(client)
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json(_REGISTER)
        assert ws.receive_json() == {"type": "registered"}
        send_malformed(ws)
        ws.send_json(_event_envelope(dc_id))  # valid event proves the channel survived
    with get_connection() as conn:
        events = RuntimeEventRepository(conn).list_by_devcontainer(dc_id)
        assert [e.event_type for e in events] == ["devcontainer_started"]
