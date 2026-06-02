"""Tests for SSE invalidation broadcast after projection commits (VIB-45)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient
from vibing_protocol import RuntimeEvent

from vibing_api.core.broadcaster import SseEvent
from vibing_api.core.reducer import invalidations_for
from vibing_api.core.runtime_channel import persist_runtime_event
from vibing_api.core.schema import apply_schema
from vibing_api.repositories.agent_sessions import AgentSessionRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository

_SOURCE = "host_runtime_worker"
_DC = "dc-1"
_SESSION = "sess-1"


def _event(event_type: str, **kwargs: object) -> RuntimeEvent:
    return RuntimeEvent(event_type=event_type, source=_SOURCE, **kwargs)


# ---------------------------------------------------------------------------
# Pure unit tests: invalidations_for()
# ---------------------------------------------------------------------------


class TestInvalidationsForDevcontainer:
    def test_starting(self) -> None:
        evts = invalidations_for(_event("devcontainer_starting", devcontainer_id=_DC))
        assert evts == [SseEvent(scope="devcontainers", ids=[_DC])]

    def test_started(self) -> None:
        evts = invalidations_for(_event("devcontainer_started", devcontainer_id=_DC))
        assert evts == [SseEvent(scope="devcontainers", ids=[_DC])]

    def test_stopping(self) -> None:
        evts = invalidations_for(_event("devcontainer_stopping", devcontainer_id=_DC))
        assert evts == [SseEvent(scope="devcontainers", ids=[_DC])]

    def test_stopped(self) -> None:
        evts = invalidations_for(_event("devcontainer_stopped", devcontainer_id=_DC))
        assert evts == [SseEvent(scope="devcontainers", ids=[_DC])]

    def test_failed(self) -> None:
        evts = invalidations_for(_event("devcontainer_failed", devcontainer_id=_DC))
        assert evts == [SseEvent(scope="devcontainers", ids=[_DC])]

    def test_no_devcontainer_id(self) -> None:
        evts = invalidations_for(_event("devcontainer_started"))
        assert evts == [SseEvent(scope="devcontainers", ids=[])]


class TestInvalidationsForAgentSessions:
    def test_agent_session_started(self) -> None:
        evts = invalidations_for(_event("agent_session_started", agent_session_id=_SESSION))
        assert evts == [SseEvent(scope="agent_sessions", ids=[_SESSION])]

    def test_session_stopped(self) -> None:
        evts = invalidations_for(_event("session_stopped", agent_session_id=_SESSION))
        assert evts == [SseEvent(scope="agent_sessions", ids=[_SESSION])]

    def test_session_completed_emits_agent_sessions_and_inbox(self) -> None:
        evts = invalidations_for(_event("session_completed", agent_session_id=_SESSION))
        scopes = {e.scope for e in evts}
        assert "agent_sessions" in scopes
        assert "inbox" in scopes
        for e in evts:
            if e.scope == "agent_sessions":
                assert e.ids == [_SESSION]
            if e.scope == "inbox":
                assert e.ids == [_SESSION]

    def test_session_failed_emits_agent_sessions_and_inbox(self) -> None:
        evts = invalidations_for(_event("session_failed", agent_session_id=_SESSION))
        scopes = {e.scope for e in evts}
        assert "agent_sessions" in scopes
        assert "inbox" in scopes


class TestInvalidationsForApprovals:
    def test_approval_requested_all_three_scopes(self) -> None:
        evts = invalidations_for(
            _event(
                "approval_requested",
                agent_session_id=_SESSION,
                devcontainer_id=_DC,
                payload={"requested_action": "rm -rf"},
            )
        )
        scopes = {e.scope for e in evts}
        # AC2: agent_sessions, approvals, inbox all invalidated
        assert scopes == {"agent_sessions", "approvals", "inbox"}
        for e in evts:
            if e.scope == "agent_sessions":
                assert e.ids == [_SESSION]

    def test_approval_resolved_all_three_scopes(self) -> None:
        evts = invalidations_for(
            _event(
                "approval_resolved",
                agent_session_id=_SESSION,
                payload={"resolution": "approved", "approval_request_id": "ar-42"},
            )
        )
        scopes = {e.scope for e in evts}
        assert scopes == {"agent_sessions", "approvals", "inbox"}
        for e in evts:
            if e.scope == "approvals":
                assert "ar-42" in e.ids


class TestInvalidationsForInbox:
    def test_agent_asked_question(self) -> None:
        evts = invalidations_for(_event("agent_asked_question", devcontainer_id=_DC))
        assert evts == [SseEvent(scope="inbox", ids=[_DC])]

    def test_user_input_sent(self) -> None:
        evts = invalidations_for(_event("user_input_sent", payload={"inbox_event_id": "inbox-99"}))
        assert evts == [SseEvent(scope="inbox", ids=["inbox-99"])]

    def test_user_input_sent_missing_payload(self) -> None:
        evts = invalidations_for(_event("user_input_sent"))
        assert evts == [SseEvent(scope="inbox", ids=[])]


# ---------------------------------------------------------------------------
# AC7: agent session + approval status change produce expected invalidations
# ---------------------------------------------------------------------------


def test_approval_requested_emits_agent_sessions_invalidation() -> None:
    evts = invalidations_for(
        _event("approval_requested", agent_session_id=_SESSION, devcontainer_id=_DC)
    )
    agent_evts = [e for e in evts if e.scope == "agent_sessions"]
    assert len(agent_evts) == 1
    assert _SESSION in agent_evts[0].ids


def test_approval_resolved_emits_approvals_invalidation() -> None:
    approval_id = "ar-123"
    evts = invalidations_for(
        _event(
            "approval_resolved",
            agent_session_id=_SESSION,
            payload={"resolution": "approved", "approval_request_id": approval_id},
        )
    )
    approval_evts = [e for e in evts if e.scope == "approvals"]
    assert len(approval_evts) == 1
    assert approval_id in approval_evts[0].ids


def test_session_completed_emits_agent_sessions_invalidation() -> None:
    evts = invalidations_for(_event("session_completed", agent_session_id=_SESSION))
    agent_evts = [e for e in evts if e.scope == "agent_sessions"]
    assert len(agent_evts) == 1
    assert _SESSION in agent_evts[0].ids


# ---------------------------------------------------------------------------
# Integration: persist_runtime_event broadcasts AFTER commit (AC1)
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection)
    connection.commit()
    return connection


class CapturingBroadcaster:
    """Spy broadcaster that records all published events."""

    def __init__(self) -> None:
        self.published: list[SseEvent] = []

    def publish(self, event: SseEvent) -> None:
        self.published.append(event)


def test_persist_broadcasts_after_commit(client: TestClient) -> None:
    """Invalidations fire after the DB commit; DB state is visible when they fire."""
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/tmp/dc"})
    assert resp.status_code == 201
    dc_id = resp.json()["id"]

    broadcaster = CapturingBroadcaster()
    event = RuntimeEvent(
        event_type="devcontainer_started",
        source=_SOURCE,
        devcontainer_id=dc_id,
    )
    persist_runtime_event(event, broadcaster)  # type: ignore[arg-type]

    # (a) read-model committed
    from vibing_api.core.database import get_connection

    with get_connection() as conn:
        dc = DevcontainerRepository(conn).get(dc_id)
    assert dc.status == "running"

    # (b) invalidation published
    assert len(broadcaster.published) == 1
    assert broadcaster.published[0].scope == "devcontainers"
    assert dc_id in broadcaster.published[0].ids


def test_persist_agent_session_broadcasts(client: TestClient) -> None:
    """APPROVAL_REQUESTED invalidates agent_sessions, approvals, and inbox."""
    resp = client.post("/api/v1/devcontainers", json={"name": "dc2", "local_path": "/tmp/dc2"})
    dc_id = resp.json()["id"]

    from vibing_api.core.database import get_connection

    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(dc_id)
        conn.commit()
    session_id = session.id

    broadcaster = CapturingBroadcaster()
    event = RuntimeEvent(
        event_type="approval_requested",
        source=_SOURCE,
        devcontainer_id=dc_id,
        agent_session_id=session_id,
        payload={"requested_action": "do something"},
    )
    persist_runtime_event(event, broadcaster)  # type: ignore[arg-type]

    scopes = {e.scope for e in broadcaster.published}
    assert scopes == {"agent_sessions", "approvals", "inbox"}


def test_failed_projection_does_not_broadcast(client: TestClient) -> None:
    """A projection that raises must not publish any invalidations (AC1)."""
    broadcaster = CapturingBroadcaster()
    event = RuntimeEvent(
        event_type="approval_resolved",
        source=_SOURCE,
        payload={"resolution": "invalid_value"},  # will raise ValueError in reduce()
    )
    with pytest.raises(ValueError):
        persist_runtime_event(event, broadcaster)  # type: ignore[arg-type]

    assert broadcaster.published == []
