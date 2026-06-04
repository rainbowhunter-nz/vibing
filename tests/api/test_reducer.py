import sqlite3

import pytest
from vibing_protocol import RuntimeEvent

from vibing_api.core.reducer import (
    ProjectionUpdates,
    inbox_event_type_for,
    project,
    reduce,
)
from vibing_api.core.schema import apply_schema
from vibing_api.repositories.agent_sessions import AgentSessionRepository
from vibing_api.repositories.approvals import ApprovalRepository
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.inbox import InboxRepository
from vibing_api.repositories.summaries import SessionSummaryRepository

_SOURCE = "devcontainer_runtime_agent"


# --- pure layer -----------------------------------------------------------


def test_inbox_event_type_for_known_mappings() -> None:
    assert inbox_event_type_for("agent_asked_question") == "question"
    assert inbox_event_type_for("approval_requested") == "approval_request"
    assert inbox_event_type_for("session_completed") == "completion"
    assert inbox_event_type_for("session_failed") == "failure"


def test_inbox_event_type_for_unmapped_returns_none() -> None:
    for event_type in (
        "devcontainer_starting",
        "devcontainer_started",
        "devcontainer_stopping",
        "devcontainer_stopped",
        "devcontainer_failed",
        "agent_session_started",
        "approval_resolved",
        "user_input_sent",
        "session_stopped",
    ):
        assert inbox_event_type_for(event_type) is None


def _event(event_type: str, **kwargs: object) -> RuntimeEvent:
    return RuntimeEvent(event_type=event_type, source=_SOURCE, **kwargs)


def test_reduce_devcontainer_lifecycle() -> None:
    assert reduce(_event("devcontainer_starting")).devcontainer_status == "starting"
    assert reduce(_event("devcontainer_started")).devcontainer_status == "running"
    assert reduce(_event("devcontainer_stopping")).devcontainer_status == "stopping"
    assert reduce(_event("devcontainer_stopped")).devcontainer_status == "stopped"
    assert reduce(_event("devcontainer_failed")).devcontainer_status == "error"


def test_reduce_agent_session_started() -> None:
    assert reduce(_event("agent_session_started")).session_status == "running"


def test_reduce_approval_requested() -> None:
    updates = reduce(_event("approval_requested", payload={"requested_action": "rm -rf"}))
    assert updates == ProjectionUpdates(
        session_status="waiting_for_approval",
        create_approval=True,
        requested_action="rm -rf",
        inbox_event_type="approval_request",
    )


def test_reduce_approval_resolved() -> None:
    updates = reduce(
        _event(
            "approval_resolved", payload={"resolution": "approved", "approval_request_id": "ar-1"}
        )
    )
    assert updates == ProjectionUpdates(
        session_status="running",
        resolve_approval="approved",
        resolve_approval_id="ar-1",
        resolve_linked_inbox=True,
    )


def test_reduce_agent_asked_question() -> None:
    assert reduce(_event("agent_asked_question")).inbox_event_type == "question"


def test_reduce_agent_asked_question_captures_content() -> None:
    updates = reduce(_event("agent_asked_question", payload={"question": "Redis or in-memory?"}))
    assert updates.inbox_event_type == "question"
    assert updates.inbox_content == "Redis or in-memory?"


def test_reduce_agent_asked_question_without_payload_has_no_content() -> None:
    assert reduce(_event("agent_asked_question")).inbox_content is None


def test_reduce_terminal_paths() -> None:
    completed = reduce(_event("session_completed"))
    assert completed.session_status == "completed"
    assert completed.final_status == "completed"
    assert completed.inbox_event_type == "completion"

    failed = reduce(_event("session_failed"))
    assert failed.session_status == "failed"
    assert failed.final_status == "failed"
    assert failed.inbox_event_type == "failure"

    stopped = reduce(_event("session_stopped"))
    assert stopped.session_status == "stopped"
    assert stopped.final_status == "stopped"
    assert stopped.inbox_event_type is None


def test_reduce_session_completed_captures_result() -> None:
    updates = reduce(_event("session_completed", payload={"result": "All 42 tests passed."}))
    assert updates.inbox_content == "All 42 tests passed."
    assert updates.summary_text == "All 42 tests passed."


def test_reduce_session_completed_without_result_has_no_content() -> None:
    updates = reduce(_event("session_completed"))
    assert updates.inbox_content is None
    assert updates.summary_text is None


def test_reduce_session_failed_captures_stderr_tail() -> None:
    updates = reduce(_event("session_failed", payload={"stderr_tail": "Error: ENOENT"}))
    assert updates.inbox_content == "Error: ENOENT"
    assert updates.summary_text == "Error: ENOENT"


def test_reduce_session_failed_without_stderr_tail_has_no_content() -> None:
    updates = reduce(_event("session_failed"))
    assert updates.inbox_content is None
    assert updates.summary_text is None


def test_reduce_approval_resolved_missing_resolution() -> None:
    with pytest.raises(ValueError, match="payload.resolution"):
        reduce(_event("approval_resolved", payload={}))


def test_reduce_approval_resolved_invalid_resolution() -> None:
    with pytest.raises(ValueError, match="payload.resolution"):
        reduce(_event("approval_resolved", payload={"resolution": "maybe"}))


# --- projection integration ----------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    apply_schema(connection)
    connection.commit()
    return connection


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> tuple[str, str]:
    dc = DevcontainerRepository(conn).create("dc", "/tmp/dc")
    session = AgentSessionRepository(conn).create(dc.id)
    return dc.id, session.id


def _emit(
    conn: sqlite3.Connection,
    dc_id: str,
    session_id: str,
    event_type: str,
    payload: dict | None = None,
) -> None:
    project(
        RuntimeEvent(
            event_type=event_type,
            source=_SOURCE,
            devcontainer_id=dc_id,
            agent_session_id=session_id,
            payload=payload,
        ),
        conn,
    )


def test_devcontainer_status_transitions(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    repo = DevcontainerRepository(conn)

    _emit(conn, dc_id, session_id, "devcontainer_starting")
    assert repo.get(dc_id).status == "starting"
    _emit(conn, dc_id, session_id, "devcontainer_started")
    assert repo.get(dc_id).status == "running"
    _emit(conn, dc_id, session_id, "devcontainer_stopping")
    assert repo.get(dc_id).status == "stopping"
    _emit(conn, dc_id, session_id, "devcontainer_stopped")
    assert repo.get(dc_id).status == "stopped"
    _emit(conn, dc_id, session_id, "devcontainer_failed")
    assert repo.get(dc_id).status == "error"


def test_agent_session_started(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    _emit(conn, dc_id, session_id, "agent_session_started")
    assert AgentSessionRepository(conn).get(session_id).status == "running"


def test_approval_round_trip_approved(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    sessions = AgentSessionRepository(conn)
    approvals = ApprovalRepository(conn)
    inbox = InboxRepository(conn)

    _emit(conn, dc_id, session_id, "approval_requested", {"requested_action": "delete files"})
    assert sessions.get(session_id).status == "waiting_for_approval"
    pending = approvals.get_pending_by_session(session_id)
    assert pending is not None
    assert pending.requested_action == "delete files"
    linked = inbox.get_by_approval(pending.id)
    assert linked is not None
    assert linked.event_type == "approval_request"
    assert linked.status == "unread"

    _emit(
        conn,
        dc_id,
        session_id,
        "approval_resolved",
        {"resolution": "approved", "approval_request_id": pending.id},
    )
    assert sessions.get(session_id).status == "running"
    assert approvals.get(pending.id).status == "approved"
    assert approvals.get(pending.id).decided_at is not None
    assert inbox.get(linked.id).status == "resolved"
    assert approvals.get_pending_by_session(session_id) is None


def test_approval_round_trip_rejected(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    approvals = ApprovalRepository(conn)
    inbox = InboxRepository(conn)

    _emit(conn, dc_id, session_id, "approval_requested", {"requested_action": "x"})
    pending = approvals.get_pending_by_session(session_id)
    linked = inbox.get_by_approval(pending.id)

    _emit(
        conn,
        dc_id,
        session_id,
        "approval_resolved",
        {"resolution": "rejected", "approval_request_id": pending.id},
    )
    assert approvals.get(pending.id).status == "rejected"
    assert inbox.get(linked.id).status == "resolved"
    assert AgentSessionRepository(conn).get(session_id).status == "running"


def test_approval_resolved_without_pending_is_noop(
    conn: sqlite3.Connection, seeded: tuple[str, str]
) -> None:
    dc_id, session_id = seeded

    # unknown approval_request_id → no-op (tolerate out-of-order / missing rows)
    _emit(
        conn,
        dc_id,
        session_id,
        "approval_resolved",
        {"resolution": "approved", "approval_request_id": "does-not-exist"},
    )

    rows = conn.execute(
        "SELECT id FROM approval_requests WHERE agent_session_id = ?", (session_id,)
    ).fetchall()
    assert rows == []


def test_user_input_sent_resolves_question_inbox(
    conn: sqlite3.Connection, seeded: tuple[str, str]
) -> None:
    dc_id, session_id = seeded
    sessions = AgentSessionRepository(conn)
    inbox = InboxRepository(conn)

    # Seed a question inbox event via agent_asked_question
    _emit(conn, dc_id, session_id, "agent_asked_question")
    question = inbox.list(agent_session_id=session_id)[0]
    assert question.event_type == "question"
    assert question.status == "unread"

    # Session is still running (agent_asked_question does not change session status)
    _emit(conn, dc_id, session_id, "agent_session_started")

    # user_input_sent should resolve the inbox event, not change session status
    _emit(conn, dc_id, session_id, "user_input_sent", {"inbox_event_id": question.id})

    assert inbox.get(question.id).status == "resolved"
    # session status unchanged
    assert sessions.get(session_id).status == "running"


def test_user_input_sent_missing_inbox_event_is_noop(
    conn: sqlite3.Connection, seeded: tuple[str, str]
) -> None:
    dc_id, session_id = seeded
    # emit with a non-existent inbox_event_id — tolerate gracefully
    _emit(conn, dc_id, session_id, "user_input_sent", {"inbox_event_id": "does-not-exist"})
    # No exception, no state change
    rows = conn.execute(
        "SELECT id FROM inbox_events WHERE agent_session_id = ?", (session_id,)
    ).fetchall()
    assert rows == []


def test_reduce_user_input_sent() -> None:
    updates = reduce(_event("user_input_sent", payload={"inbox_event_id": "inbox-42"}))
    assert updates == ProjectionUpdates(resolve_inbox_event_id="inbox-42")


def test_inbox_event_skipped_when_devcontainer_id_absent(conn: sqlite3.Connection) -> None:
    # Out-of-order tolerance: an inbox-producing event with no devcontainer_id
    # is dropped rather than inserted against a missing parent.
    project(RuntimeEvent(event_type="agent_asked_question", source=_SOURCE), conn)
    rows = conn.execute("SELECT id FROM inbox_events").fetchall()
    assert rows == []


def test_agent_asked_question_creates_inbox(
    conn: sqlite3.Connection, seeded: tuple[str, str]
) -> None:
    dc_id, session_id = seeded
    _emit(conn, dc_id, session_id, "agent_asked_question")
    rows = conn.execute(
        "SELECT event_type, status FROM inbox_events WHERE agent_session_id = ?",
        (session_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "question"
    assert rows[0]["status"] == "unread"


def test_agent_asked_question_persists_content(
    conn: sqlite3.Connection, seeded: tuple[str, str]
) -> None:
    dc_id, session_id = seeded
    project(
        RuntimeEvent(
            event_type="agent_asked_question",
            source=_SOURCE,
            devcontainer_id=dc_id,
            agent_session_id=session_id,
            payload={"question": "Redis or in-memory?"},
        ),
        conn,
    )
    row = conn.execute(
        "SELECT content FROM inbox_events WHERE agent_session_id = ?",
        (session_id,),
    ).fetchone()
    assert row[0] == "Redis or in-memory?"


def test_session_completed(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    _emit(conn, dc_id, session_id, "session_completed")
    assert AgentSessionRepository(conn).get(session_id).status == "completed"
    summary = SessionSummaryRepository(conn).get_by_session(session_id)
    assert summary is not None
    assert summary.final_status == "completed"
    assert summary.last_known_event == "session_completed"
    assert summary.summary_text is None
    rows = conn.execute(
        "SELECT event_type, status FROM inbox_events WHERE agent_session_id = ?",
        (session_id,),
    ).fetchall()
    assert (rows[0]["event_type"], rows[0]["status"]) == ("completion", "unread")


def test_session_completed_with_result(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    _emit(conn, dc_id, session_id, "session_completed", {"result": "All 42 tests passed."})
    summary = SessionSummaryRepository(conn).get_by_session(session_id)
    assert summary.summary_text == "All 42 tests passed."
    row = conn.execute(
        "SELECT content FROM inbox_events WHERE agent_session_id = ?", (session_id,)
    ).fetchone()
    assert row["content"] == "All 42 tests passed."
    # status unchanged
    assert AgentSessionRepository(conn).get(session_id).status == "completed"


def test_session_failed(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    _emit(conn, dc_id, session_id, "session_failed")
    assert AgentSessionRepository(conn).get(session_id).status == "failed"
    summary = SessionSummaryRepository(conn).get_by_session(session_id)
    assert summary.final_status == "failed"
    rows = conn.execute(
        "SELECT event_type, status FROM inbox_events WHERE agent_session_id = ?",
        (session_id,),
    ).fetchall()
    assert (rows[0]["event_type"], rows[0]["status"]) == ("failure", "unread")


def test_session_failed_with_stderr_tail(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    _emit(conn, dc_id, session_id, "session_failed", {"stderr_tail": "Error: ENOENT"})
    summary = SessionSummaryRepository(conn).get_by_session(session_id)
    assert summary.summary_text == "Error: ENOENT"
    row = conn.execute(
        "SELECT content FROM inbox_events WHERE agent_session_id = ?", (session_id,)
    ).fetchone()
    assert row["content"] == "Error: ENOENT"
    # status unchanged
    assert AgentSessionRepository(conn).get(session_id).status == "failed"


def test_session_stopped_no_inbox(conn: sqlite3.Connection, seeded: tuple[str, str]) -> None:
    dc_id, session_id = seeded
    _emit(conn, dc_id, session_id, "session_stopped")
    assert AgentSessionRepository(conn).get(session_id).status == "stopped"
    summary = SessionSummaryRepository(conn).get_by_session(session_id)
    assert summary.final_status == "stopped"
    rows = conn.execute(
        "SELECT id FROM inbox_events WHERE agent_session_id = ?", (session_id,)
    ).fetchall()
    assert rows == []


# --- Explicit target: resolves EXACT approval by id, not just any pending ---


def test_approval_resolved_targets_exact_approval_approve(
    conn: sqlite3.Connection, seeded: tuple[str, str]
) -> None:
    """Resolving approval A by id leaves approval B untouched."""
    dc_id, session_id = seeded
    approvals = ApprovalRepository(conn)
    inbox = InboxRepository(conn)

    # Seed two approvals directly (bypassing the event path to avoid session-status conflicts)
    approval_a = approvals.create(dc_id, session_id, "action A")
    inbox_a = inbox.create(dc_id, "approval_request", "unread", session_id, approval_a.id)
    approval_b = approvals.create(dc_id, session_id, "action B")
    inbox_b = inbox.create(dc_id, "approval_request", "unread", session_id, approval_b.id)

    # Resolve only approval A
    _emit(
        conn,
        dc_id,
        session_id,
        "approval_resolved",
        {"resolution": "approved", "approval_request_id": approval_a.id},
    )

    assert approvals.get(approval_a.id).status == "approved"
    assert inbox.get(inbox_a.id).status == "resolved"
    # approval B untouched
    assert approvals.get(approval_b.id).status == "pending"
    assert inbox.get(inbox_b.id).status == "unread"


def test_approval_resolved_targets_exact_approval_reject(
    conn: sqlite3.Connection, seeded: tuple[str, str]
) -> None:
    """Resolving approval B by id leaves approval A untouched."""
    dc_id, session_id = seeded
    approvals = ApprovalRepository(conn)
    inbox = InboxRepository(conn)

    approval_a = approvals.create(dc_id, session_id, "action A")
    inbox_a = inbox.create(dc_id, "approval_request", "unread", session_id, approval_a.id)
    approval_b = approvals.create(dc_id, session_id, "action B")
    inbox_b = inbox.create(dc_id, "approval_request", "unread", session_id, approval_b.id)

    _emit(
        conn,
        dc_id,
        session_id,
        "approval_resolved",
        {"resolution": "rejected", "approval_request_id": approval_b.id},
    )

    assert approvals.get(approval_b.id).status == "rejected"
    assert inbox.get(inbox_b.id).status == "resolved"
    # approval A untouched
    assert approvals.get(approval_a.id).status == "pending"
    assert inbox.get(inbox_a.id).status == "unread"
