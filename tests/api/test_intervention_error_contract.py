"""Contract tests: full frontend-relevant error envelope for stale User Intervention targets.

Each test drives a real endpoint and asserts HTTP status + the full error body shape
(code, message, details) so the frontend has stable, verified guarantees.
"""

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection
from vibing_api.core.errors import (
    APPROVAL_REQUEST_NOT_FOUND,
    APPROVAL_REQUEST_NOT_PENDING,
    INBOX_EVENT_NOT_ACTIONABLE,
    INBOX_EVENT_NOT_FOUND,
)
from vibing_api.repositories.agent_sessions import AgentSessionRepository
from vibing_api.repositories.approvals import ApprovalRepository
from vibing_api.repositories.inbox import InboxRepository
from api.test_error_responses import _assert_error_shape

AGENT_WS_URL = "/api/v1/runtime/agent/ws"


# --- helpers ---


def _create_dc(client: TestClient) -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work"})
    assert resp.status_code == 201
    dc_id: str = resp.json()["id"]
    client.patch(f"/api/v1/devcontainers/{dc_id}", json={"status": "running"})
    return dc_id


def _agent_register(devcontainer_id: str) -> dict:
    return {
        "type": "runtime_registered",
        "source": "devcontainer_runtime_agent",
        "devcontainer_id": devcontainer_id,
    }


def _user_input_url(dc_id: str, session_id: str) -> str:
    return f"/api/v1/devcontainers/{dc_id}/agent-sessions/{session_id}/user-input"


def _approval_resolution_url(dc_id: str, session_id: str) -> str:
    return f"/api/v1/devcontainers/{dc_id}/agent-sessions/{session_id}/approval-resolution"


def _seed_session(dc_id: str, status: str = "running") -> str:
    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(dc_id, status=status)
        conn.commit()
    return session.id


def _seed_question(session_id: str, dc_id: str) -> str:
    with get_connection() as conn:
        event = InboxRepository(conn).create(
            devcontainer_id=dc_id,
            event_type="question",
            status="unread",
            agent_session_id=session_id,
        )
        conn.commit()
    return event.id


def _seed_pending_approval(session_id: str, dc_id: str) -> str:
    with get_connection() as conn:
        approval = ApprovalRepository(conn).create(
            devcontainer_id=dc_id,
            agent_session_id=session_id,
            requested_action="some action",
        )
        InboxRepository(conn).create(
            devcontainer_id=dc_id,
            event_type="approval_request",
            status="unread",
            agent_session_id=session_id,
            approval_request_id=approval.id,
        )
        conn.commit()
    return approval.id


# ============================================================
# INBOX_EVENT_NOT_FOUND (404)
# ============================================================


def test_inbox_event_not_found_contract_missing_id(client: TestClient) -> None:
    """Event ID that doesn't exist → 404 INBOX_EVENT_NOT_FOUND with full envelope."""
    dc_id = _create_dc(client)
    session_id = _seed_session(dc_id)

    resp = client.post(
        _user_input_url(dc_id, session_id),
        json={"inbox_event_id": "ghost-inbox", "text": "answer"},
    )

    assert resp.status_code == 404
    body = resp.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == INBOX_EVENT_NOT_FOUND


def test_inbox_event_not_found_contract_wrong_session(client: TestClient) -> None:
    """Event belonging to a different session is treated as not-found (ownership mismatch)."""
    dc_id = _create_dc(client)
    session1_id = _seed_session(dc_id)
    session2_id = _seed_session(dc_id)
    inbox_id = _seed_question(session1_id, dc_id)

    resp = client.post(
        _user_input_url(dc_id, session2_id),
        json={"inbox_event_id": inbox_id, "text": "answer"},
    )

    assert resp.status_code == 404
    body = resp.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == INBOX_EVENT_NOT_FOUND


# ============================================================
# INBOX_EVENT_NOT_ACTIONABLE (409)
# ============================================================


def test_inbox_event_not_actionable_contract_wrong_type(client: TestClient) -> None:
    """Approval-request inbox event sent to user-input → 409 INBOX_EVENT_NOT_ACTIONABLE."""
    dc_id = _create_dc(client)
    session_id = _seed_session(dc_id)
    with get_connection() as conn:
        approval_inbox = InboxRepository(conn).create(
            devcontainer_id=dc_id,
            event_type="approval_request",
            status="unread",
            agent_session_id=session_id,
        )
        conn.commit()

    resp = client.post(
        _user_input_url(dc_id, session_id),
        json={"inbox_event_id": approval_inbox.id, "text": "yes"},
    )

    assert resp.status_code == 409
    body = resp.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == INBOX_EVENT_NOT_ACTIONABLE


def test_inbox_event_not_actionable_contract_already_resolved(client: TestClient) -> None:
    """Already-resolved question → 409 INBOX_EVENT_NOT_ACTIONABLE with full envelope."""
    dc_id = _create_dc(client)
    session_id = _seed_session(dc_id)
    with get_connection() as conn:
        inbox_event = InboxRepository(conn).create(
            devcontainer_id=dc_id,
            event_type="question",
            status="unread",
            agent_session_id=session_id,
        )
        InboxRepository(conn).resolve(inbox_event.id)
        conn.commit()

    resp = client.post(
        _user_input_url(dc_id, session_id),
        json={"inbox_event_id": inbox_event.id, "text": "answer"},
    )

    assert resp.status_code == 409
    body = resp.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == INBOX_EVENT_NOT_ACTIONABLE


# ============================================================
# APPROVAL_REQUEST_NOT_FOUND (404)
# ============================================================


def test_approval_request_not_found_contract_missing_id(client: TestClient) -> None:
    """Approval ID that doesn't exist → 404 APPROVAL_REQUEST_NOT_FOUND with full envelope."""
    dc_id = _create_dc(client)
    session_id = _seed_session(dc_id, status="waiting_for_approval")

    resp = client.post(
        _approval_resolution_url(dc_id, session_id),
        json={"approval_request_id": "ghost-approval", "resolution": "approved"},
    )

    assert resp.status_code == 404
    body = resp.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == APPROVAL_REQUEST_NOT_FOUND


def test_approval_request_not_found_contract_wrong_session(client: TestClient) -> None:
    """Approval belonging to a different session is treated as not-found (ownership mismatch)."""
    dc_id = _create_dc(client)
    session1_id = _seed_session(dc_id, status="waiting_for_approval")
    session2_id = _seed_session(dc_id, status="waiting_for_approval")
    approval_id = _seed_pending_approval(session1_id, dc_id)

    resp = client.post(
        _approval_resolution_url(dc_id, session2_id),
        json={"approval_request_id": approval_id, "resolution": "approved"},
    )

    assert resp.status_code == 404
    body = resp.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == APPROVAL_REQUEST_NOT_FOUND


# ============================================================
# APPROVAL_REQUEST_NOT_PENDING (409)
# ============================================================


@pytest.mark.parametrize("resolution", ["approved", "rejected"])
def test_approval_request_not_pending_contract(client: TestClient, resolution: str) -> None:
    """Already-resolved approval → 409 APPROVAL_REQUEST_NOT_PENDING with full envelope."""
    dc_id = _create_dc(client)
    session_id = _seed_session(dc_id, status="waiting_for_approval")
    with get_connection() as conn:
        approval = ApprovalRepository(conn).create(
            devcontainer_id=dc_id,
            agent_session_id=session_id,
            requested_action="some action",
        )
        ApprovalRepository(conn).resolve(approval.id, resolution)
        conn.commit()

    resp = client.post(
        _approval_resolution_url(dc_id, session_id),
        json={"approval_request_id": approval.id, "resolution": "approved"},
    )

    assert resp.status_code == 409
    body = resp.json()
    _assert_error_shape(body)
    assert body["error"]["code"] == APPROVAL_REQUEST_NOT_PENDING
