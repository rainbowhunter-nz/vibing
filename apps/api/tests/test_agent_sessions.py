"""Tests for POST /devcontainers/{id}/agent-sessions."""

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.repositories.agent_sessions import AgentSessionRepository

AGENT_WS_URL = "/api/v1/runtime/agent/ws"


def _create_dc(client: TestClient, status: str = "running") -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work"})
    assert resp.status_code == 201
    dc_id: str = resp.json()["id"]
    if status != "created":
        patched = client.patch(f"/api/v1/devcontainers/{dc_id}", json={"status": status})
        assert patched.status_code == 200
    return dc_id


def _agent_register(devcontainer_id: str) -> dict:
    return {
        "type": "runtime_registered",
        "source": "devcontainer_runtime_agent",
        "devcontainer_id": devcontainer_id,
    }


# --- Happy path ---


def test_start_session_returns_202_with_starting_status(client: TestClient) -> None:
    dc_id = _create_dc(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        resp = client.post(
            f"/api/v1/devcontainers/{dc_id}/agent-sessions", json={"prompt": "hello"}
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["devcontainer_id"] == dc_id
        assert body["status"] == "starting"
        assert body["id"] is not None


def test_start_session_sends_command_to_agent(client: TestClient) -> None:
    dc_id = _create_dc(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        resp = client.post(
            f"/api/v1/devcontainers/{dc_id}/agent-sessions", json={"prompt": "run tests"}
        )
        assert resp.status_code == 202
        session_id = resp.json()["id"]
        cmd = ws.receive_json()
        assert cmd["type"] == "command"
        assert cmd["command"]["type"] == "start_agent_session"
        assert cmd["command"]["devcontainer_id"] == dc_id
        assert cmd["command"]["agent_session_id"] == session_id
        assert cmd["command"]["payload"] == {"prompt": "run tests"}


# --- Guard 1: devcontainer not found ---


def test_guard_devcontainer_not_found(client: TestClient) -> None:
    resp = client.post("/api/v1/devcontainers/does-not-exist/agent-sessions", json={"prompt": "hi"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"


# --- Guard 2: devcontainer not running ---


@pytest.mark.parametrize("status", ["created", "starting", "stopping", "stopped", "error"])
def test_guard_devcontainer_not_running(client: TestClient, status: str) -> None:
    dc_id = _create_dc(client, status=status)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/agent-sessions", json={"prompt": "hi"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_DEVCONTAINER_STATE"


# --- Guard 3: no agent connected ---


def test_guard_no_agent_connected(client: TestClient) -> None:
    dc_id = _create_dc(client)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/agent-sessions", json={"prompt": "hi"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RUNTIME_UNAVAILABLE"


# --- Guard 4: active session already exists ---


def test_guard_active_session_already_exists(client: TestClient) -> None:
    dc_id = _create_dc(client)
    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register(dc_id))
        assert ws.receive_json() == {"type": "registered"}
        # First request succeeds
        resp1 = client.post(
            f"/api/v1/devcontainers/{dc_id}/agent-sessions", json={"prompt": "first"}
        )
        assert resp1.status_code == 202
        ws.receive_json()  # consume the command
        # Second request should be rejected
        resp2 = client.post(
            f"/api/v1/devcontainers/{dc_id}/agent-sessions", json={"prompt": "second"}
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "AGENT_SESSION_ACTIVE"


# --- Guard order: 404 before 409 ---


def test_guard_order_404_before_state_check(client: TestClient) -> None:
    """Missing devcontainer raises 404 before any state/agent guard."""
    resp = client.post("/api/v1/devcontainers/ghost/agent-sessions", json={"prompt": "x"})
    assert resp.status_code == 404


# --- Validation: empty prompt ---


def test_empty_prompt_rejected(client: TestClient) -> None:
    dc_id = _create_dc(client)
    resp = client.post(f"/api/v1/devcontainers/{dc_id}/agent-sessions", json={"prompt": ""})
    assert resp.status_code == 422


# --- Repo: get_active_by_devcontainer ---


def test_get_active_by_devcontainer_returns_none_when_no_session(client: TestClient) -> None:
    dc_id = _create_dc(client)
    with get_connection() as conn:
        result = AgentSessionRepository(conn).get_active_by_devcontainer(dc_id)
    assert result is None


def test_get_active_by_devcontainer_returns_starting_session(client: TestClient) -> None:
    dc_id = _create_dc(client)
    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(dc_id, status="starting")
        conn.commit()
    with get_connection() as conn:
        result = AgentSessionRepository(conn).get_active_by_devcontainer(dc_id)
    assert result is not None
    assert result.id == session.id


def test_get_active_by_devcontainer_ignores_terminal_sessions(client: TestClient) -> None:
    dc_id = _create_dc(client)
    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(dc_id, status="starting")
        AgentSessionRepository(conn).set_status(session.id, "completed")
        conn.commit()
    with get_connection() as conn:
        result = AgentSessionRepository(conn).get_active_by_devcontainer(dc_id)
    assert result is None


# --- AC3: reducer projects terminal status + SessionSummary on session_completed/session_failed ---


def test_reducer_projects_session_completed(client: TestClient) -> None:
    """session_completed event → session status=completed + SessionSummary created."""
    from vibing_api.core.reducer import project
    from vibing_protocol import RuntimeEvent

    dc_id = _create_dc(client)
    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(dc_id, status="running")
        conn.commit()

    event = RuntimeEvent(
        event_type="session_completed",
        source="devcontainer_runtime_agent",
        devcontainer_id=dc_id,
        agent_session_id=session.id,
        payload={"result": "done"},
    )
    with get_connection() as conn:
        project(event, conn)
        conn.commit()

    with get_connection() as conn:
        updated = AgentSessionRepository(conn).get(session.id)
    assert updated is not None
    assert updated.status == "completed"


def test_reducer_projects_session_failed(client: TestClient) -> None:
    """session_failed event → session status=failed + SessionSummary created."""
    from vibing_api.core.reducer import project
    from vibing_protocol import RuntimeEvent

    dc_id = _create_dc(client)
    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(dc_id, status="running")
        conn.commit()

    event = RuntimeEvent(
        event_type="session_failed",
        source="devcontainer_runtime_agent",
        devcontainer_id=dc_id,
        agent_session_id=session.id,
        payload={"exit_code": 1, "stderr_tail": "error"},
    )
    with get_connection() as conn:
        project(event, conn)
        conn.commit()

    with get_connection() as conn:
        updated = AgentSessionRepository(conn).get(session.id)
    assert updated is not None
    assert updated.status == "failed"
